"""Unit tests for src/rfbridge/bridge.py — Tasmota discovery forwarding."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt
import pytest

from src.rfbridge.bridge import RfBridgeConfig, RfBridgeMqttBridge
from src.rfbridge.protocol import DecodedFrame


MINIMAL_CFG = {
    "internal_broker": {"host": "localhost", "port": 11883},
    "central_broker": {"host": "localhost", "port": 1883},
    "logging": {"level": "DEBUG"},
}


@pytest.fixture
def bridge(tmp_path):
    sensors_yaml = tmp_path / "sensors.yaml"
    sensors_yaml.write_text("sensors: {}\n")
    cfg = RfBridgeConfig(MINIMAL_CFG)
    with patch("src.rfbridge.bridge.mqtt.Client", return_value=MagicMock()):
        b = RfBridgeMqttBridge(cfg, sensors_yaml)
    b._central.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
    return b


def _make_discovery_msg(topic: str, payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload).encode()
    return msg


class TestTasmotaDiscoveryForwarding:
    def test_internal_connect_subscribes_to_discovery(self, bridge):
        client = MagicMock()
        bridge._on_internal_connect(client, None, {}, 0)
        topics = [c.args[0] for c in client.subscribe.call_args_list]
        assert "tasmota/discovery/#" in topics

    def test_discovery_message_forwarded_to_central(self, bridge):
        payload = {"ip": "10.0.0.1", "hn": "433rfbridge"}
        msg = _make_discovery_msg("tasmota/discovery/AABBCC/config", payload)
        bridge._forward_tasmota_discovery(msg)
        bridge._central.publish.assert_called_once_with(
            "tasmota/discovery/AABBCC/config",
            msg.payload,
            qos=1,
            retain=True,
        )

    def test_discovery_message_cached(self, bridge):
        payload = {"ip": "10.0.0.1", "hn": "433rfbridge"}
        msg = _make_discovery_msg("tasmota/discovery/AABBCC/config", payload)
        bridge._forward_tasmota_discovery(msg)
        assert "tasmota/discovery/AABBCC/config" in bridge._tasmota_discovery_cache
        assert bridge._tasmota_discovery_cache["tasmota/discovery/AABBCC/config"] == msg.payload

    def test_multiple_discovery_topics_cached(self, bridge):
        for subtopic in ("config", "sensors"):
            msg = _make_discovery_msg(f"tasmota/discovery/AABBCC/{subtopic}", {"data": subtopic})
            bridge._forward_tasmota_discovery(msg)
        assert len(bridge._tasmota_discovery_cache) == 2

    def test_on_message_routes_discovery_to_forwarder(self, bridge):
        payload = {"ip": "10.0.0.1"}
        msg = _make_discovery_msg("tasmota/discovery/AABBCC/config", payload)
        with patch.object(bridge, "_forward_tasmota_discovery") as mock_fwd:
            bridge._on_message(None, None, msg)
        mock_fwd.assert_called_once_with(msg)

    def test_on_message_does_not_route_non_discovery(self, bridge):
        msg = MagicMock()
        msg.topic = "tele/433rfbridge/RESULT"
        msg.payload = b'{"RfRaw": {}}'
        with patch.object(bridge, "_forward_tasmota_discovery") as mock_fwd:
            bridge._on_message(None, None, msg)
        mock_fwd.assert_not_called()

    def test_cache_replay_on_central_reconnect(self, bridge):
        raw = b'{"ip":"10.0.0.1"}'
        bridge._tasmota_discovery_cache["tasmota/discovery/AABBCC/config"] = raw
        bridge._forward_tasmota_discovery_cache()
        bridge._central.publish.assert_called_once_with(
            "tasmota/discovery/AABBCC/config", raw, qos=1, retain=True
        )

    def test_cache_replay_publishes_all_entries(self, bridge):
        bridge._tasmota_discovery_cache["tasmota/discovery/AA/config"] = b'{"a":1}'
        bridge._tasmota_discovery_cache["tasmota/discovery/AA/sensors"] = b'{"b":2}'
        bridge._forward_tasmota_discovery_cache()
        assert bridge._central.publish.call_count == 2

    def test_empty_cache_replay_publishes_nothing(self, bridge):
        bridge._forward_tasmota_discovery_cache()
        bridge._central.publish.assert_not_called()

    def test_central_connect_triggers_cache_replay(self, bridge):
        bridge._tasmota_discovery_cache["tasmota/discovery/AA/config"] = b'{"a":1}'
        with patch.object(bridge, "_publish_startup_discovery"):
            bridge._on_central_connect(bridge._central, None, {}, 0)
        topics = [c.args[0] for c in bridge._central.publish.call_args_list]
        assert "tasmota/discovery/AA/config" in topics

    def test_forward_failure_does_not_raise(self, bridge):
        bridge._central.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_NO_CONN)
        msg = _make_discovery_msg("tasmota/discovery/AABBCC/config", {"ip": "1.2.3.4"})
        bridge._forward_tasmota_discovery(msg)  # should not raise
        # Message still cached even on publish failure
        assert "tasmota/discovery/AABBCC/config" in bridge._tasmota_discovery_cache


def _make_frame() -> DecodedFrame:
    return DecodedFrame(
        protocol="nexus_compatible",
        sof=0,
        device_id=0xAB,
        battery_ok=True,
        tx_button=False,
        channel=1,
        temperature=21.0,
        humidity=50,
        raw_data="AA B1 ...",
    )


class TestPublishStateSanitisation:
    def test_state_topic_sanitises_spaces(self, bridge):
        frame = _make_frame()
        bridge._publish_state("EG Wohnzimmer", frame)
        topic = bridge._central.publish.call_args.args[0]
        assert " " not in topic
        assert topic == "tele/433rfbridge/EG_Wohnzimmer/state"

    def test_state_topic_sanitises_umlauts(self, bridge):
        frame = _make_frame()
        bridge._publish_state("EG Wohnküche", frame)
        topic = bridge._central.publish.call_args.args[0]
        assert "ü" not in topic
        assert topic == "tele/433rfbridge/EG_Wohnkueche/state"

    def test_state_topic_matches_discovery_state_topic(self, bridge):
        from src.rfbridge.ha_discovery import make_temperature_discovery_payload
        raw_name = "EG Wohnküche"
        frame = _make_frame()
        bridge._publish_state(raw_name, frame)
        published_topic = bridge._central.publish.call_args.args[0]
        # Strip the /state suffix to get the prefix for comparison
        discovery_payload = make_temperature_discovery_payload(raw_name, "nexus_compatible", 1, "tele/433rfbridge")
        assert discovery_payload["state_topic"] == published_topic
