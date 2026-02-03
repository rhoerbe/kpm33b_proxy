"""Config sender for KPM33B meters.

Discovers meters via central broker, sends upload frequency configuration
to meters via internal broker, and verifies acknowledgements.
"""

import json
import logging
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt

from src.config import AppConfig, PROJECT_ROOT

logger = logging.getLogger(__name__)

BACKOFF_BASE = 1
BACKOFF_MAX = 60
ACK_TIMEOUT = 3.0


def _make_oprid() -> str:
    """Generate a 32-char hex nonce for oprid."""
    return uuid.uuid4().hex


def _meter_id_last8(meter_id: str) -> str:
    return meter_id[-8:]


class ConfigSender:
    def __init__(self, config: AppConfig):
        self.config = config
        self.known_meters: set[str] = set()
        self._pending_acks: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._config_mtime: float = 0.0
        self._config_path = PROJECT_ROOT / "config.yaml"
        self._stop_event = threading.Event()
        self._setup_central_client()
        self._setup_internal_client()

    def _setup_central_client(self) -> None:
        self.central_client = mqtt.Client(client_id="kpm33b_config_central", protocol=mqtt.MQTTv311)
        self.central_client.on_connect = self._on_central_connect
        self.central_client.on_disconnect = self._on_central_disconnect
        self.central_client.on_message = self._on_central_message

    def _setup_internal_client(self) -> None:
        self.internal_client = mqtt.Client(client_id="kpm33b_config_internal", protocol=mqtt.MQTTv311)
        self.internal_client.on_connect = self._on_internal_connect
        self.internal_client.on_disconnect = self._on_internal_disconnect
        self.internal_client.on_message = self._on_internal_message

    def _on_central_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc != 0:
            logger.error("Central broker connection failed: rc=%d", rc)
            return
        logger.info("Config sender connected to central broker")
        discovery_topic = f"{self.config.central_broker_topics.external_main_topic}/+/seconds"
        client.subscribe(discovery_topic)
        logger.info("Subscribed to %s for meter discovery", discovery_topic)

    def _on_central_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected disconnect from central broker (rc=%d), will reconnect", rc)

    def _on_central_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        """Handle discovery messages from central broker."""
        parts = msg.topic.split("/")
        if len(parts) < 3:
            return
        meter_id = parts[-2]
        if meter_id not in self.known_meters:
            logger.info("Discovered new meter: %s", meter_id)
            self.known_meters.add(meter_id)
            self._send_config_to_meter(meter_id)

    def _on_internal_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc != 0:
            logger.error("Internal broker connection failed: rc=%d", rc)
            return
        logger.info("Config sender connected to internal broker")
        ack_topic = self.config.internal_broker_topics.meter_settime_ack
        client.subscribe(ack_topic)
        logger.info("Subscribed to %s for ack messages", ack_topic)

    def _on_internal_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected disconnect from internal broker (rc=%d), will reconnect", rc)

    def _on_internal_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        """Handle ack messages from meters on the internal broker."""
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.error("Invalid JSON ack on %s: %s", msg.topic, msg.payload[:200])
            return
        oprid = payload.get("oprid")
        if oprid is None:
            return
        with self._lock:
            event = self._pending_acks.pop(oprid, None)
        if event is not None:
            event.set()

    def _send_config_to_meter(self, meter_id: str) -> None:
        """Send seconds and minutes upload frequency config to a single meter."""
        last8 = _meter_id_last8(meter_id)
        topic_prefix = self.config.internal_broker_topics.meter_settime
        topic = f"{topic_prefix}{last8}"
        meters_cfg = self.config.kpm33b_meters

        self._send_command(topic, meter_id, cmd="0000", value=str(meters_cfg.upload_frequency_seconds))
        self._send_command(topic, meter_id, cmd="0001", value=str(meters_cfg.upload_frequency_minutes))

    def _send_command(self, topic: str, meter_id: str, cmd: str, value: str) -> None:
        oprid = _make_oprid()
        payload = json.dumps({"oprid": oprid, "Cmd": cmd, "value": value, "types": "1"})

        ack_event = threading.Event()
        with self._lock:
            self._pending_acks[oprid] = ack_event

        result = self.internal_client.publish(topic, payload, qos=1)
        cmd_label = "seconds" if cmd == "0000" else "minutes"
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Publish config %s to %s failed: rc=%d", cmd_label, topic, result.rc)
            with self._lock:
                self._pending_acks.pop(oprid, None)
            return

        logger.info("Sent %s config to meter %s (oprid=%s, value=%s)", cmd_label, meter_id, oprid, value)

        if ack_event.wait(timeout=ACK_TIMEOUT):
            logger.info("Ack received for meter %s %s config (oprid=%s)", meter_id, cmd_label, oprid)
        else:
            logger.log(logging.CRITICAL, "ALERT: No ack from meter %s for %s config (oprid=%s) within %.0fs",
                        meter_id, cmd_label, oprid, ACK_TIMEOUT)
            with self._lock:
                self._pending_acks.pop(oprid, None)

    def _check_config_mtime(self) -> None:
        """Check if config.yaml was modified and re-send config to all known meters."""
        try:
            mtime = self._config_path.stat().st_mtime
        except OSError:
            return
        if self._config_mtime == 0.0:
            self._config_mtime = mtime
            return
        if mtime > self._config_mtime:
            self._config_mtime = mtime
            logger.info("config.yaml changed, re-sending config to all %d known meters", len(self.known_meters))
            for meter_id in list(self.known_meters):
                self._send_config_to_meter(meter_id)

    def connect(self) -> None:
        self._connect_with_backoff(
            self.central_client,
            self.config.central_broker.host,
            self.config.central_broker.port,
            "central",
        )
        self._connect_with_backoff(
            self.internal_client,
            self.config.internal_broker.host,
            self.config.internal_broker.port,
            "internal",
        )

    def _connect_with_backoff(self, client: mqtt.Client, host: str, port: int, label: str) -> None:
        delay = BACKOFF_BASE
        while True:
            try:
                client.connect(host, port, keepalive=60)
                return
            except OSError as e:
                logger.warning("Connection to %s broker at %s:%d failed: %s — retrying in %ds",
                               label, host, port, e, delay)
                time.sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX)

    def start(self) -> None:
        """Start MQTT loops and config file monitoring."""
        self.central_client.loop_start()
        self.internal_client.loop_start()
        self._monitor_thread = threading.Thread(target=self._monitor_config_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Config sender started")

    def _monitor_config_loop(self) -> None:
        while not self._stop_event.is_set():
            self._check_config_mtime()
            self._stop_event.wait(timeout=5.0)

    def stop(self) -> None:
        self._stop_event.set()
        self.central_client.loop_stop()
        self.internal_client.loop_stop()
        self.central_client.disconnect()
        self.internal_client.disconnect()
        logger.info("Config sender stopped")
