"""Integration test: end-to-end data flow through two local mosquitto brokers.

Requires `mosquitto` server binary to be installed.
Skips automatically if unavailable.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest

from src.bridge import MqttBridge
from src.config import AppConfig

MOSQUITTO_BIN = shutil.which("mosquitto") or shutil.which("mosquitto", path="/usr/sbin:/usr/local/sbin")
pytestmark = pytest.mark.skipif(MOSQUITTO_BIN is None, reason="mosquitto server not installed")

INTERNAL_PORT = 18830
CENTRAL_PORT = 18831
TEST_MSG_DIR = Path(__file__).resolve().parent.parent / "test_msg"


@pytest.fixture
def config(tmp_path):
    """AppConfig pointing to ephemeral local broker ports."""
    cfg = {
        "internal_broker": {"host": "127.0.0.1", "port": INTERNAL_PORT},
        "central_broker": {"host": "127.0.0.1", "port": CENTRAL_PORT},
        "internal_broker_topics": {
            "meter_seconds_data": "MQTT_RT_DATA",
            "meter_minutes_data": "MQTT_ENY_NOW",
            "meter_settime": "MQTT_COMMOD_SET_",
            "meter_settime_ack": "MQTT_COMMOD_READ_REP",
        },
        "central_broker_topics": {
            "external_main_topic": "kpm33b",
            "status_topic": "kpm33b/status",
        },
        "logging": {"level": "DEBUG", "file": str(tmp_path / "test.log")},
        "kpm33b_meters": {"upload_frequency_seconds": 5, "upload_frequency_minutes": 1},
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

    time.sleep(1)  # wait for brokers to start

    for proc, label in [(internal_proc, "internal"), (central_proc, "central")]:
        if proc.poll() is not None:
            pytest.fail(f"{label} mosquitto failed to start: {proc.stderr.read().decode()}")

    yield

    internal_proc.terminate()
    central_proc.terminate()
    internal_proc.wait(timeout=5)
    central_proc.wait(timeout=5)


class TestDataFlowEndToEnd:
    def test_rt_data_forwarded(self, config, brokers):
        """Publish MQTT_RT_DATA to internal broker, verify transformed output on central broker."""
        bridge = MqttBridge(config)
        bridge.connect()
        bridge.start()
        time.sleep(0.5)

        received = []
        done = __import__("threading").Event()

        def on_message(client, userdata, msg):
            received.append((msg.topic, json.loads(msg.payload)))
            done.set()

        subscriber = mqtt.Client(client_id="test_subscriber", protocol=mqtt.MQTTv311)
        subscriber.on_message = on_message
        subscriber.connect("127.0.0.1", CENTRAL_PORT)
        subscriber.subscribe("kpm33b/+/seconds")
        subscriber.loop_start()
        time.sleep(0.5)

        raw = json.loads((TEST_MSG_DIR / "MQTT_RT_DATA.json").read_text())
        publisher = mqtt.Client(client_id="test_publisher", protocol=mqtt.MQTTv311)
        publisher.connect("127.0.0.1", INTERNAL_PORT)
        publisher.publish("MQTT_RT_DATA", json.dumps(raw), qos=1)
        publisher.disconnect()

        done.wait(timeout=5)
        bridge.stop()
        subscriber.loop_stop()
        subscriber.disconnect()

        assert len(received) == 1
        topic, payload = received[0]
        assert topic == "kpm33b/33B1225950027/seconds"
        assert payload["active_power"] == 6.6905
        assert payload["id"] == "33B1225950027"

    def test_eny_now_forwarded(self, config, brokers):
        """Publish MQTT_ENY_NOW to internal broker, verify transformed output on central broker."""
        bridge = MqttBridge(config)
        bridge.connect()
        bridge.start()
        time.sleep(0.5)

        received = []
        done = __import__("threading").Event()

        def on_message(client, userdata, msg):
            received.append((msg.topic, json.loads(msg.payload)))
            done.set()

        subscriber = mqtt.Client(client_id="test_subscriber", protocol=mqtt.MQTTv311)
        subscriber.on_message = on_message
        subscriber.connect("127.0.0.1", CENTRAL_PORT)
        subscriber.subscribe("kpm33b/+/minutes")
        subscriber.loop_start()
        time.sleep(0.5)

        raw = json.loads((TEST_MSG_DIR / "MQTT_ENY_NOW.json").read_text())
        publisher = mqtt.Client(client_id="test_publisher", protocol=mqtt.MQTTv311)
        publisher.connect("127.0.0.1", INTERNAL_PORT)
        publisher.publish("MQTT_ENY_NOW", json.dumps(raw), qos=1)
        publisher.disconnect()

        done.wait(timeout=5)
        bridge.stop()
        subscriber.loop_stop()
        subscriber.disconnect()

        assert len(received) == 1
        topic, payload = received[0]
        assert topic == "kpm33b/33B1225950027/minutes"
        assert payload["active_energy"] == 163.486
        assert payload["id"] == "33B1225950027"
