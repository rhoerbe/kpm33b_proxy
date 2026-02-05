"""MQTT two-broker bridge for KPM33B proxy.

Subscribes to internal broker topics, transforms messages,
and publishes simplified data to the central broker.
Also publishes Home Assistant autodiscovery messages for new meters.
"""

import json
import logging
import time

import paho.mqtt.client as mqtt

from src.config import AppConfig
from src.ha_discovery import publish_discovery
from src.transform import IsendError, transform_eny_now, transform_rt_data

logger = logging.getLogger(__name__)

BACKOFF_BASE = 1
BACKOFF_MAX = 60


class MqttBridge:
    def __init__(self, config: AppConfig):
        self.config = config
        self.discovered_meters: set[str] = set()
        self._setup_internal_client()
        self._setup_central_client()

    def _setup_internal_client(self) -> None:
        self.internal_client = mqtt.Client(client_id="kpm33b_proxy_internal", protocol=mqtt.MQTTv311)
        if self.config.internal_broker.username:
            self.internal_client.username_pw_set(self.config.internal_broker.username, self.config.internal_broker.password)
        self.internal_client.on_connect = self._on_internal_connect
        self.internal_client.on_disconnect = self._on_internal_disconnect
        self.internal_client.on_message = self._on_internal_message

    def _setup_central_client(self) -> None:
        self.central_client = mqtt.Client(client_id="kpm33b_proxy_central", protocol=mqtt.MQTTv311)
        if self.config.central_broker.username:
            self.central_client.username_pw_set(self.config.central_broker.username, self.config.central_broker.password)
        self.central_client.on_connect = self._on_central_connect
        self.central_client.on_disconnect = self._on_central_disconnect

    def _on_internal_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc != 0:
            logger.error("Internal broker connection failed: rc=%d", rc)
            return
        logger.info("Connected to internal broker")
        topics = self.config.internal_broker_topics
        client.subscribe(topics.meter_seconds_data)
        client.subscribe(topics.meter_minutes_data)
        logger.info("Subscribed to %s, %s", topics.meter_seconds_data, topics.meter_minutes_data)

    def _on_internal_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected disconnect from internal broker (rc=%d), will reconnect", rc)

    def _on_central_connect(self, client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc != 0:
            logger.error("Central broker connection failed: rc=%d", rc)
            return
        logger.info("Connected to central broker")

    def _on_central_disconnect(self, client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected disconnect from central broker (rc=%d), will reconnect", rc)

    def _on_internal_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        try:
            raw = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.error("Invalid JSON on topic %s: %s", topic, msg.payload[:200])
            return

        topics = self.config.internal_broker_topics
        main_topic = self.config.central_broker_topics.external_main_topic

        try:
            if topic == topics.meter_seconds_data:
                transformed = transform_rt_data(raw)
                device_id = transformed.get("id", "unknown")
                target_topic = f"{main_topic}/{device_id}/seconds"
            elif topic == topics.meter_minutes_data:
                transformed = transform_eny_now(raw)
                device_id = transformed.get("id", "unknown")
                target_topic = f"{main_topic}/{device_id}/minutes"
            else:
                logger.debug("Ignoring message on unhandled topic %s", topic)
                return
        except IsendError as e:
            logger.error("Data validation error on topic %s: %s", topic, e)
            return

        # Publish HA autodiscovery on first message from a new meter
        if device_id not in self.discovered_meters and device_id != "unknown":
            self.discovered_meters.add(device_id)
            logger.info("New meter discovered: %s — publishing HA autodiscovery", device_id)
            publish_discovery(self.central_client, device_id, main_topic)

        payload = json.dumps(transformed)
        result = self.central_client.publish(target_topic, payload, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug("Published to %s", target_topic)
        else:
            logger.error("Publish to %s failed: rc=%d", target_topic, result.rc)

    def connect(self) -> None:
        """Connect to both brokers with retry logic."""
        self._connect_with_backoff(
            self.internal_client,
            self.config.internal_broker.host,
            self.config.internal_broker.port,
            "internal",
        )
        self._connect_with_backoff(
            self.central_client,
            self.config.central_broker.host,
            self.config.central_broker.port,
            "central",
        )

    def _connect_with_backoff(self, client: mqtt.Client, host: str, port: int, label: str) -> None:
        delay = BACKOFF_BASE
        while True:
            try:
                client.connect(host, port, keepalive=60)
                return
            except OSError as e:
                logger.warning("Connection to %s broker at %s:%d failed: %s — retrying in %ds", label, host, port, e, delay)
                time.sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX)

    def start(self) -> None:
        """Start both MQTT client loops (non-blocking, threaded)."""
        self.internal_client.loop_start()
        self.central_client.loop_start()
        logger.info("MQTT bridge started")

    def stop(self) -> None:
        """Disconnect and stop both MQTT client loops."""
        self.internal_client.loop_stop()
        self.central_client.loop_stop()
        self.internal_client.disconnect()
        self.central_client.disconnect()
        logger.info("MQTT bridge stopped")
