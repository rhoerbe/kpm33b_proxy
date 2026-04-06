"""MQTT bridge for Sonoff RF Bridge R2 / Portisch / Tasmota proxy.

Subscribes to the central broker for raw AA B1 RF frames published by Tasmota,
decodes them, maps device IDs to friendly sensor names, and publishes structured JSON
back to the central broker. Also manages Home Assistant autodiscovery and RfRaw mode
resilience via the Tasmota HTTP API.

Tasmota publishes to the internal broker (same as kpm33b_proxy); decoded data is
forwarded to the central broker. An optional `rfbridge_input_broker` config section
overrides the subscription broker if the Tasmota device is configured differently.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt

from src.rfbridge.ha_discovery import clear_discovery, publish_discovery
from src.rfbridge.protocol import DecodedFrame, parse_rfraw_payload
from src.rfbridge.sensor_registry import DeadSensorRegistry, Deduplicator, SensorRegistry

logger = logging.getLogger(__name__)

BACKOFF_BASE = 1
BACKOFF_MAX = 60


class RfBridgeConfig:
    """Configuration holder for the RF bridge proxy."""

    def __init__(self, cfg: dict):
        # Tasmota publishes to the internal broker; use rfbridge_input_broker to override if needed
        broker = cfg.get("rfbridge_input_broker") or cfg["internal_broker"]
        self.internal_host: str = broker["host"]
        self.internal_port: int = broker["port"]
        self.internal_username: str | None = broker.get("username")
        self.internal_password: str | None = broker.get("password")

        broker = cfg["central_broker"]
        self.central_host: str = broker["host"]
        self.central_port: int = broker["port"]
        self.central_username: str | None = broker.get("username")
        self.central_password: str | None = broker.get("password")

        topics = cfg.get("tasmota_bridge_topics", {})
        self.input_topic: str = topics.get("input_topic", "tele/433rfbridge/RESULT")
        self.discovery_topic: str = topics.get("discovery_topic", "tele/433rfbridge/discovery")
        self.output_topic_prefix: str = topics.get("output_topic_prefix", "tele/433rfbridge")

        proxy = cfg.get("rfbridge_proxy", {})
        self.sensor_timeout_seconds: int = proxy.get("sensor_timeout_seconds", 3600)
        self.migration_window_seconds: int = proxy.get("migration_window_seconds", 900)
        self.dedup_window_seconds: int = proxy.get("dedup_window_seconds", 30)
        self.outlier_temp_delta: float = proxy.get("outlier_temp_delta", 10.0)
        self.tasmota_http_host: str = proxy.get("tasmota_http_host", "")
        self.tasmota_http_port: int = proxy.get("tasmota_http_port", 80)
        self.rfraw_mode: int = proxy.get("rfraw_mode", 177)
        self.rfraw_check_interval_seconds: int = proxy.get("rfraw_check_interval_seconds", 300)

        self.logging_level: str = cfg.get("logging", {}).get("level", "INFO")


class RfBridgeMqttBridge:
    """Two-broker MQTT bridge for the 433 MHz RF bridge proxy."""

    def __init__(self, config: RfBridgeConfig, sensors_path: Path):
        self.config = config
        self._registry = SensorRegistry(sensors_path, config.sensor_timeout_seconds)
        self._dead_registry = DeadSensorRegistry(config.migration_window_seconds)
        self._dedup = Deduplicator(config.dedup_window_seconds, config.outlier_temp_delta)
        self._discovered_sensors: set[str] = set()
        self._previously_published_names: set[str] = set(self._registry._sensors)
        self._last_message_time: float = 0.0
        # Cache of retained tasmota/discovery/# messages received from the internal broker.
        # Re-published to the central broker on every central connect (mirrors HA discovery logic).
        self._tasmota_discovery_cache: dict[str, bytes] = {}  # topic → raw payload
        self._setup_internal_client()
        self._setup_central_client()

    def _setup_internal_client(self) -> None:
        self._internal = mqtt.Client(client_id="433rfbridge_proxy_internal", protocol=mqtt.MQTTv311)
        if self.config.internal_username:
            self._internal.username_pw_set(self.config.internal_username, self.config.internal_password)
        self._internal.on_connect = self._on_internal_connect
        self._internal.on_disconnect = self._on_internal_disconnect
        self._internal.on_message = self._on_message

    def _setup_central_client(self) -> None:
        self._central = mqtt.Client(client_id="433rfbridge_proxy_central", protocol=mqtt.MQTTv311)
        if self.config.central_username:
            self._central.username_pw_set(self.config.central_username, self.config.central_password)
        self._central.on_connect = self._on_central_connect
        self._central.on_disconnect = self._on_central_disconnect

    # ── MQTT callbacks ──────────────────────────────────────────────────────────

    def _on_internal_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc != 0:
            logger.error("Internal broker connection failed: rc=%d", rc)
            return
        logger.info("Connected to internal broker")
        client.subscribe(self.config.input_topic)
        client.subscribe("tasmota/discovery/#")
        logger.info("Subscribed to %s and tasmota/discovery/#", self.config.input_topic)

    def _on_internal_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected disconnect from internal broker (rc=%d), will reconnect", rc)

    def _on_central_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc != 0:
            logger.error("Central broker connection failed: rc=%d", rc)
            return
        logger.info("Connected to central broker")
        self._publish_startup_discovery()
        self._forward_tasmota_discovery_cache()

    def _on_central_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected disconnect from central broker (rc=%d), will reconnect", rc)

    # ── Message handling ────────────────────────────────────────────────────────

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        if msg.topic.startswith("tasmota/discovery/"):
            self._forward_tasmota_discovery(msg)
            return

        self._last_message_time = time.time()
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.error("Invalid JSON on %s: %.200s", msg.topic, msg.payload)
            return

        rfraw = payload.get("RfRaw", {})
        raw_hex = rfraw.get("Data", "")
        if not raw_hex:
            logger.debug("No RfRaw.Data in payload on %s", msg.topic)
            return

        frame = parse_rfraw_payload(raw_hex)
        if frame is None:
            return  # already logged by parser

        if frame.battery_ok is False:
            logger.warning("Battery low on channel %d (device_id=%s)", frame.channel, frame.device_id_hex)

        if self._dedup.is_duplicate_or_outlier(
            frame.protocol, frame.channel, frame.device_id, frame.temperature, frame.humidity
        ):
            return

        self._route_frame(frame)

    def _forward_tasmota_discovery(self, msg: mqtt.MQTTMessage) -> None:
        """Cache and forward a single Tasmota discovery message to the central broker."""
        self._tasmota_discovery_cache[msg.topic] = bytes(msg.payload)
        result = self._central.publish(msg.topic, msg.payload, qos=1, retain=True)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Forwarded %s to central broker", msg.topic)
        else:
            logger.error("Failed to forward %s: rc=%d", msg.topic, result.rc)

    def _forward_tasmota_discovery_cache(self) -> None:
        """Re-publish all cached Tasmota discovery messages to the central broker.

        Called on every central broker connect so retained messages are restored
        after a central broker restart or manual deletion.
        """
        for topic, payload in self._tasmota_discovery_cache.items():
            self._central.publish(topic, payload, qos=1, retain=True)
        if self._tasmota_discovery_cache:
            logger.info("Forwarded %d Tasmota discovery entries to central broker", len(self._tasmota_discovery_cache))

    def _route_frame(self, frame: DecodedFrame) -> None:
        """Look up sensor name and publish decoded state, or route to discovery."""
        friendly_name = self._registry.lookup(frame.protocol, frame.channel)

        if friendly_name is None and frame.channel == 1:
            # Fallback: check DeadSensorRegistry for sensors without a channel switch
            migrated = self._dead_registry.check_for_battery_swap(
                frame.device_id_hex, frame.protocol, frame.channel
            )
            if migrated:
                logger.info("Auto-migrated sensor '%s' to new ID %s", migrated, frame.device_id_hex)
                self._registry.register_new_sensor(migrated, frame.protocol, frame.channel, frame.device_id_hex)
                self._notify_migration(migrated, frame.device_id_hex)
                friendly_name = migrated

        if friendly_name is None:
            self._publish_discovery_frame(frame)
            return

        id_changed = self._registry.update_last_seen(friendly_name, frame.device_id_hex)
        if id_changed:
            logger.info("Sensor '%s' appeared with new device ID %s (battery swap?)", friendly_name, frame.device_id_hex)

        if friendly_name not in self._discovered_sensors:
            self._discovered_sensors.add(friendly_name)
            cfg = self._registry._sensors[friendly_name]
            publish_discovery(self._central, friendly_name, cfg["protocol"], cfg["channel"], self.config.output_topic_prefix)

        self._publish_state(friendly_name, frame)

    def _publish_state(self, friendly_name: str, frame: DecodedFrame) -> None:
        topic = f"{self.config.output_topic_prefix}/{friendly_name}/state"
        payload = json.dumps({
            "temperature": frame.temperature,
            "humidity": frame.humidity,
            "battery_low": not frame.battery_ok,
            "channel": frame.channel,
            "device_id": frame.device_id_hex,
            "raw_source": frame.raw_data,
        })
        result = self._central.publish(topic, payload, qos=1, retain=True)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug("Published state for '%s' to %s", friendly_name, topic)
        else:
            logger.error("Publish to %s failed: rc=%d", topic, result.rc)

    def _publish_discovery_frame(self, frame: DecodedFrame) -> None:
        """Publish unknown sensor data to the discovery topic for manual configuration."""
        payload = json.dumps({
            "temperature": frame.temperature,
            "humidity": frame.humidity,
            "battery_low": not frame.battery_ok,
            "channel": frame.channel,
            "device_id": frame.device_id_hex,
            "protocol": frame.protocol,
            "raw_source": frame.raw_data,
        })
        result = self._central.publish(self.config.discovery_topic, payload, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(
                "Unknown sensor published to discovery: proto=%s ch=%d id=%s T=%.1f H=%d",
                frame.protocol, frame.channel, frame.device_id_hex, frame.temperature, frame.humidity,
            )

    def _publish_startup_discovery(self) -> None:
        """Publish HA autodiscovery for all configured sensors on startup.

        Clears retained discovery topics for any names that were previously published
        but are no longer in sensors.yaml (handles renames and removals).
        """
        current_names = set(self._registry._sensors)
        for stale_name in self._previously_published_names - current_names:
            logger.info("Sensor '%s' removed/renamed — clearing stale HA discovery", stale_name)
            clear_discovery(self._central, stale_name)

        for friendly_name, cfg in self._registry._sensors.items():
            publish_discovery(
                self._central, friendly_name, cfg["protocol"], cfg["channel"],
                self.config.output_topic_prefix,
            )
            self._discovered_sensors.add(friendly_name)

        self._previously_published_names = current_names

    def _notify_migration(self, friendly_name: str, new_id: str) -> None:
        """Notify Home Assistant of an auto-migrated sensor via MQTT."""
        topic = "homeassistant/notify/433rfbridge"
        payload = json.dumps({
            "title": "RF Proxy Alert",
            "message": f"Sensor '{friendly_name}' re-appeared with new ID {new_id}. sensors.yaml updated automatically.",
        })
        self._central.publish(topic, payload, qos=1)

    # ── RfRaw mode resilience ───────────────────────────────────────────────────

    def _check_rfraw_mode(self) -> None:
        """Re-issue RfRaw 177 command if no messages received within the check interval."""
        if not self.config.tasmota_http_host:
            return
        now = time.time()
        if self._last_message_time == 0.0:
            return  # haven't received any message yet; don't spam at startup
        elapsed = now - self._last_message_time
        if elapsed < self.config.rfraw_check_interval_seconds:
            return

        logger.warning(
            "No RF messages for %.0fs (threshold %ds) — re-issuing RfRaw %d",
            elapsed, self.config.rfraw_check_interval_seconds, self.config.rfraw_mode,
        )
        url = (
            f"http://{self.config.tasmota_http_host}:{self.config.tasmota_http_port}"
            f"/cm?cmnd=RfRaw%20{self.config.rfraw_mode}"
        )
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode()
                logger.info("Tasmota RfRaw command response: %s", body[:200])
                self._last_message_time = time.time()  # reset to avoid repeated calls
        except urllib.error.URLError as e:
            logger.error("Failed to reach Tasmota at %s: %s", url, e)

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._connect_with_backoff(self._internal, self.config.internal_host, self.config.internal_port, "internal")
        self._connect_with_backoff(self._central, self.config.central_host, self.config.central_port, "central")

    def _connect_with_backoff(self, client: mqtt.Client, host: str, port: int, label: str) -> None:
        delay = BACKOFF_BASE
        while True:
            try:
                client.connect(host, port, keepalive=60)
                return
            except OSError as e:
                logger.warning(
                    "Connection to %s broker at %s:%d failed: %s — retrying in %ds",
                    label, host, port, e, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX)

    def start(self) -> None:
        self._internal.loop_start()
        self._central.loop_start()
        logger.info("RF bridge MQTT bridge started")

    def stop(self) -> None:
        self._internal.loop_stop()
        self._central.loop_stop()
        self._internal.disconnect()
        self._central.disconnect()
        logger.info("RF bridge MQTT bridge stopped")

    def run_maintenance(self) -> None:
        """Periodic maintenance: move dead sensors to registry, check RfRaw mode."""
        dead = self._registry.collect_dead_sensors()
        for name, data in dead.items():
            self._dead_registry.add(name, data["protocol"], data["channel"], data["last_seen"])
        self._check_rfraw_mode()
