"""Integration test with real KPM33B devices on broker 10.4.4.17.

Skips if $MQTTPW is not set.
Uses 10.4.4.17 as both internal and central broker (same broker, with auth).
The bridge subscribes to MQTT_RT_DATA / MQTT_ENY_NOW, transforms, and
publishes to kpm33b/<deviceid>/seconds and kpm33b/<deviceid>/minutes.
This test verifies the full pipeline with real device data.

Observation window: 5 minutes (RT_DATA defaults to 30s, ENY_NOW to 1 min).
"""

import json
import os
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from src.bridge import MqttBridge
from src.config import AppConfig

BROKER_HOST = "10.4.4.17"
BROKER_PORT = 1883
MQTT_USER = "mqtt"
MQTT_PASS = os.environ.get("MQTTPW")
TIMEOUT_SECONDS_DATA = 300    # 5 minutes — RT_DATA defaults to 30s
TIMEOUT_MINUTES_DATA = 28800  # 8 hours — ENY_NOW interval may be long

pytestmark = pytest.mark.skipif(MQTT_PASS is None, reason="MQTTPW env var not set")


@pytest.fixture
def config(tmp_path):
    broker_cfg = {"host": BROKER_HOST, "port": BROKER_PORT, "username": MQTT_USER, "password": MQTT_PASS}
    return AppConfig(
        internal_broker=broker_cfg,
        central_broker=broker_cfg,
        internal_broker_topics={
            "meter_seconds_data": "MQTT_RT_DATA",
            "meter_minutes_data": "MQTT_ENY_NOW",
            "meter_settime": "MQTT_COMMOD_SET_",
            "meter_settime_ack": "MQTT_COMMOD_READ_REP",
        },
        central_broker_topics={
            "external_main_topic": "kpm33b",
            "status_topic": "kpm33b/status",
        },
        logging={"level": "DEBUG", "file": str(tmp_path / "test.log")},
        kpm33b_meters={"upload_frequency_seconds": 30, "upload_frequency_minutes": 1},
    )


class TestRealDeviceDataFlow:
    def test_rt_data_from_real_device(self, config):
        """Wait for a real MQTT_RT_DATA message, verify bridge transforms and publishes it."""
        bridge = MqttBridge(config)
        bridge.connect()
        bridge.start()
        time.sleep(1)

        received = []
        done = threading.Event()

        def on_message(client, userdata, msg):
            received.append((msg.topic, json.loads(msg.payload)))
            done.set()

        subscriber = mqtt.Client(client_id="test_real_sub_seconds", protocol=mqtt.MQTTv311)
        subscriber.username_pw_set(MQTT_USER, MQTT_PASS)
        subscriber.on_message = on_message
        subscriber.connect(BROKER_HOST, BROKER_PORT)
        subscriber.subscribe("kpm33b/+/seconds")
        subscriber.loop_start()

        try:
            assert done.wait(timeout=TIMEOUT_SECONDS_DATA), \
                f"No MQTT_RT_DATA message received from real devices within {TIMEOUT_SECONDS_DATA}s"
            topic, payload = received[0]
            assert topic.startswith("kpm33b/")
            assert topic.endswith("/seconds")
            assert "id" in payload
            assert "time" in payload
            assert "active_power" in payload
            assert len(payload["id"]) == 13
        finally:
            bridge.stop()
            subscriber.loop_stop()
            subscriber.disconnect()

    def test_eny_now_from_real_device(self, config):
        """Wait for a real MQTT_ENY_NOW message, verify bridge transforms and publishes it."""
        bridge = MqttBridge(config)
        bridge.connect()
        bridge.start()
        time.sleep(1)

        received = []
        done = threading.Event()

        def on_message(client, userdata, msg):
            received.append((msg.topic, json.loads(msg.payload)))
            done.set()

        subscriber = mqtt.Client(client_id="test_real_sub_minutes", protocol=mqtt.MQTTv311)
        subscriber.username_pw_set(MQTT_USER, MQTT_PASS)
        subscriber.on_message = on_message
        subscriber.connect(BROKER_HOST, BROKER_PORT)
        subscriber.subscribe("kpm33b/+/minutes")
        subscriber.loop_start()

        try:
            assert done.wait(timeout=TIMEOUT_MINUTES_DATA), \
                f"No MQTT_ENY_NOW message received from real devices within {TIMEOUT_MINUTES_DATA}s"
            topic, payload = received[0]
            assert topic.startswith("kpm33b/")
            assert topic.endswith("/minutes")
            assert "id" in payload
            assert "time" in payload
            assert "active_energy" in payload
            assert len(payload["id"]) == 13
        finally:
            bridge.stop()
            subscriber.loop_stop()
            subscriber.disconnect()
