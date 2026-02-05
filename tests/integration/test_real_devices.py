"""Integration test with real KPM33B devices on broker 10.4.4.17.

Skips if $MQTTPW is not set.
Uses 10.4.4.17 as both internal and central broker (same broker, with auth).

Bridge tests: subscribes to MQTT_RT_DATA / MQTT_ENY_NOW, transforms, and
publishes to kpm33b/<deviceid>/seconds and kpm33b/<deviceid>/minutes.

ConfigSender tests: discovers meters, sends upload frequency configuration
(30s seconds, 1min minutes) and verifies real meter ACKs.

Observation window: 5 minutes (RT_DATA defaults to 30s, ENY_NOW to 1 min).
"""

import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from src.bridge import MqttBridge
from src.config import AppConfig
from src.config_sender import ConfigSender

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
            "meter_settime_ack": "MQTT_COMMOD_SET_REP",
        },
        central_broker_topics={
            "external_main_topic": "kpm33b",
            "status_topic": "kpm33b/status",
        },
        logging={"level": "DEBUG"},
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


METER_ID = "33B1225950028"
METER_LAST8 = "25950028"
TIMEOUT_CONFIG = 30  # seconds — generous timeout for broker round-trip


class TestRealDeviceConfigSender:
    """Send upload frequency config to a real meter via MQTT_COMMOD_SET_<last8>."""

    def test_config_sender_sets_intervals(self, config, caplog):
        """Discover meter, send 30s/1min config, verify commands published and meter ACKs."""
        caplog.set_level(logging.DEBUG)

        sender = ConfigSender(config)
        sender.connect()
        sender.start()
        time.sleep(1)

        config_topic = f"MQTT_COMMOD_SET_{METER_LAST8}"
        ack_topic = "MQTT_COMMOD_SET_REP"
        commands_received = []
        commands_done = threading.Event()
        # Track ACKs keyed by oprid so we can match against sent commands
        ack_oprids: set[str] = set()
        ack_lock = threading.Lock()

        def on_config_msg(client, userdata, msg):
            commands_received.append(json.loads(msg.payload))
            if len(commands_received) >= 2:
                commands_done.set()

        def on_ack_msg(client, userdata, msg):
            payload = json.loads(msg.payload)
            oprid = payload.get("oprid")
            if oprid:
                with ack_lock:
                    ack_oprids.add(oprid)

        # Observer for config commands on internal broker
        cmd_observer = mqtt.Client(client_id="test_cmd_observer", protocol=mqtt.MQTTv311)
        cmd_observer.username_pw_set(MQTT_USER, MQTT_PASS)
        cmd_observer.on_message = on_config_msg
        cmd_observer.connect(BROKER_HOST, BROKER_PORT)
        cmd_observer.subscribe(config_topic, qos=1)
        cmd_observer.loop_start()

        # Observer for ACK messages from real meter
        ack_observer = mqtt.Client(client_id="test_ack_observer", protocol=mqtt.MQTTv311)
        ack_observer.username_pw_set(MQTT_USER, MQTT_PASS)
        ack_observer.on_message = on_ack_msg
        ack_observer.connect(BROKER_HOST, BROKER_PORT)
        ack_observer.subscribe(ack_topic, qos=1)
        ack_observer.loop_start()
        time.sleep(0.5)

        # Trigger meter discovery
        discovery_pub = mqtt.Client(client_id="test_discovery_trigger", protocol=mqtt.MQTTv311)
        discovery_pub.username_pw_set(MQTT_USER, MQTT_PASS)
        discovery_pub.connect(BROKER_HOST, BROKER_PORT)
        discovery_msg = json.dumps({"id": METER_ID, "time": "20260204120000", "active_power": 0.0})
        discovery_pub.publish(f"kpm33b/{METER_ID}/seconds", discovery_msg, qos=1)
        discovery_pub.disconnect()

        try:
            # --- Phase 1: verify config commands were published ---
            assert commands_done.wait(timeout=TIMEOUT_CONFIG), \
                f"Config commands not observed on {config_topic} within {TIMEOUT_CONFIG}s"

            commands_received.sort(key=lambda p: p["Cmd"])

            seconds_cmd = commands_received[0]
            assert seconds_cmd["Cmd"] == "0000"
            assert seconds_cmd["value"] == "30"
            assert seconds_cmd["types"] == "1"
            assert len(seconds_cmd["oprid"]) == 32

            minutes_cmd = commands_received[1]
            assert minutes_cmd["Cmd"] == "0001"
            assert minutes_cmd["value"] == "1"
            assert minutes_cmd["types"] == "1"
            assert len(minutes_cmd["oprid"]) == 32

            # --- Phase 2: wait for ACKs from real meter ---
            sent_oprids = {c["oprid"] for c in commands_received}
            deadline = time.monotonic() + TIMEOUT_CONFIG
            while time.monotonic() < deadline:
                with ack_lock:
                    if sent_oprids.issubset(ack_oprids):
                        break
                time.sleep(0.5)

            with ack_lock:
                matched = sent_oprids & ack_oprids
                missing = sent_oprids - ack_oprids

            assert not missing, \
                f"Meter did not ACK all commands within {TIMEOUT_CONFIG}s. Missing oprids: {missing}"

            # Verify no CRITICAL alerts (meaning ACKs arrived within ACK_TIMEOUT)
            critical_records = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
            assert len(critical_records) == 0, \
                f"Unexpected CRITICAL logs: {[r.message for r in critical_records]}"

        finally:
            sender.stop()
            cmd_observer.loop_stop()
            cmd_observer.disconnect()
            ack_observer.loop_stop()
            ack_observer.disconnect()
