"""Integration test: ConfigSender sets meter upload frequency via local mosquitto brokers.

Starts two ephemeral mosquitto instances (internal + central), then verifies that
ConfigSender discovers a meter and sends the correct configuration commands.

Requires `mosquitto` server binary to be installed.
Skips automatically if unavailable.
"""

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from src.config import AppConfig
from src.config_sender import ConfigSender

MOSQUITTO_BIN = shutil.which("mosquitto") or shutil.which("mosquitto", path="/usr/sbin:/usr/local/sbin")
pytestmark = pytest.mark.skipif(MOSQUITTO_BIN is None, reason="mosquitto server not installed")

INTERNAL_PORT = 18832
CENTRAL_PORT = 18833
METER_ID = "33B1225950028"
METER_LAST8 = "25950028"


@pytest.fixture
def config(tmp_path):
    """AppConfig with upload_frequency_seconds=30 and upload_frequency_minutes=1."""
    cfg = {
        "internal_broker": {"host": "127.0.0.1", "port": INTERNAL_PORT},
        "central_broker": {"host": "127.0.0.1", "port": CENTRAL_PORT},
        "internal_broker_topics": {
            "meter_seconds_data": "MQTT_RT_DATA",
            "meter_minutes_data": "MQTT_ENY_NOW",
            "meter_settime": "MQTT_COMMOD_SET_",
            "meter_settime_ack": "MQTT_COMMOD_SET_REP",
        },
        "central_broker_topics": {
            "external_main_topic": "kpm33b",
            "status_topic": "kpm33b/status",
        },
        "logging": {"level": "DEBUG", "file": str(tmp_path / "test.log")},
        "kpm33b_meters": {"upload_frequency_seconds": 30, "upload_frequency_minutes": 1},
    }
    return AppConfig(**cfg)


def _write_mosquitto_conf(tmp_path: Path, port: int, name: str) -> Path:
    conf = tmp_path / f"{name}.conf"
    conf.write_text(f"listener {port}\nprotocol mqtt\nallow_anonymous true\npersistence false\n")
    return conf


@pytest.fixture
def brokers(tmp_path):
    """Start two local mosquitto instances and tear them down after the test."""
    internal_conf = _write_mosquitto_conf(tmp_path, INTERNAL_PORT, "internal")
    central_conf = _write_mosquitto_conf(tmp_path, CENTRAL_PORT, "central")

    internal_proc = subprocess.Popen([MOSQUITTO_BIN, "-c", str(internal_conf)], stderr=subprocess.PIPE)
    central_proc = subprocess.Popen([MOSQUITTO_BIN, "-c", str(central_conf)], stderr=subprocess.PIPE)

    time.sleep(1)

    for proc, label in [(internal_proc, "internal"), (central_proc, "central")]:
        if proc.poll() is not None:
            pytest.fail(f"{label} mosquitto failed to start: {proc.stderr.read().decode()}")

    yield

    internal_proc.terminate()
    central_proc.terminate()
    internal_proc.wait(timeout=5)
    central_proc.wait(timeout=5)


class TestConfigSenderEndToEnd:
    """ConfigSender discovers a meter and sends upload frequency configuration."""

    def test_config_commands_published(self, config, brokers):
        """Trigger meter discovery, verify two config commands arrive on the correct topic."""
        sender = ConfigSender(config)
        sender.connect()
        sender.start()
        time.sleep(0.5)

        # Subscribe to the config topic on the internal broker (as the meter would)
        config_topic = f"MQTT_COMMOD_SET_{METER_LAST8}"
        received = []
        all_received = threading.Event()

        def on_message(client, userdata, msg):
            received.append(json.loads(msg.payload))
            if len(received) >= 2:
                all_received.set()

        meter_sub = mqtt.Client(client_id="test_meter_sub", protocol=mqtt.MQTTv311)
        meter_sub.on_message = on_message
        meter_sub.connect("127.0.0.1", INTERNAL_PORT)
        meter_sub.subscribe(config_topic, qos=1)
        meter_sub.loop_start()
        time.sleep(0.5)

        # Publish a discovery message on central broker to trigger meter detection
        discovery_pub = mqtt.Client(client_id="test_discovery_pub", protocol=mqtt.MQTTv311)
        discovery_pub.connect("127.0.0.1", CENTRAL_PORT)
        discovery_msg = json.dumps({"id": METER_ID, "time": "20260204120000", "active_power": 1.5})
        discovery_pub.publish(f"kpm33b/{METER_ID}/seconds", discovery_msg, qos=1)
        discovery_pub.disconnect()

        all_received.wait(timeout=10)
        sender.stop()
        meter_sub.loop_stop()
        meter_sub.disconnect()

        assert len(received) == 2, f"Expected 2 config commands, got {len(received)}"

        # Sort by Cmd to get deterministic order (0000=seconds first, 0001=minutes second)
        received.sort(key=lambda p: p["Cmd"])

        seconds_cmd = received[0]
        assert seconds_cmd["Cmd"] == "0000"
        assert seconds_cmd["value"] == "30"
        assert seconds_cmd["types"] == "1"
        assert len(seconds_cmd["oprid"]) == 32

        minutes_cmd = received[1]
        assert minutes_cmd["Cmd"] == "0001"
        assert minutes_cmd["value"] == "1"
        assert minutes_cmd["types"] == "1"
        assert len(minutes_cmd["oprid"]) == 32

    def test_ack_received_no_alert(self, config, brokers, caplog):
        """Send ACKs for both commands, verify no CRITICAL alert is logged."""
        import logging
        caplog.set_level(logging.DEBUG)

        sender = ConfigSender(config)
        sender.connect()
        sender.start()
        time.sleep(0.5)

        # Subscribe to config topic and reply with ACKs
        config_topic = f"MQTT_COMMOD_SET_{METER_LAST8}"
        ack_topic = "MQTT_COMMOD_SET_REP"

        received_oprids = []
        all_received = threading.Event()

        def on_config_msg(client, userdata, msg):
            payload = json.loads(msg.payload)
            received_oprids.append(payload["oprid"])
            # Reply with ACK immediately
            ack_payload = json.dumps({"oprid": payload["oprid"]})
            client.publish(ack_topic, ack_payload, qos=1)
            if len(received_oprids) >= 2:
                all_received.set()

        meter_sim = mqtt.Client(client_id="test_meter_sim", protocol=mqtt.MQTTv311)
        meter_sim.on_message = on_config_msg
        meter_sim.connect("127.0.0.1", INTERNAL_PORT)
        meter_sim.subscribe(config_topic, qos=1)
        meter_sim.loop_start()
        time.sleep(0.5)

        # Trigger meter discovery
        discovery_pub = mqtt.Client(client_id="test_discovery_pub2", protocol=mqtt.MQTTv311)
        discovery_pub.connect("127.0.0.1", CENTRAL_PORT)
        discovery_msg = json.dumps({"id": METER_ID, "time": "20260204120000", "active_power": 1.5})
        discovery_pub.publish(f"kpm33b/{METER_ID}/seconds", discovery_msg, qos=1)
        discovery_pub.disconnect()

        all_received.wait(timeout=10)
        # Give time for ACK processing
        time.sleep(1)

        sender.stop()
        meter_sim.loop_stop()
        meter_sim.disconnect()

        assert len(received_oprids) == 2
        # Verify no CRITICAL/ALERT log about missing acks
        critical_records = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert len(critical_records) == 0, f"Unexpected CRITICAL logs: {[r.message for r in critical_records]}"
        # Verify positive ack log entries
        ack_logs = [r for r in caplog.records if "Ack received" in r.message]
        assert len(ack_logs) == 2, f"Expected 2 ack-received logs, got {len(ack_logs)}"
