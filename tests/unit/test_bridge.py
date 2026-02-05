"""Unit tests for src/bridge.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.bridge import MqttBridge
from src.config import AppConfig


@pytest.fixture
def config():
    return AppConfig(
        internal_broker={"host": "localhost", "port": 11883},
        central_broker={"host": "localhost", "port": 1883},
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
        kpm33b_meters={"upload_frequency_seconds": 5, "upload_frequency_minutes": 1},
    )


@pytest.fixture
def config_with_exclusion():
    return AppConfig(
        internal_broker={"host": "localhost", "port": 11883},
        central_broker={"host": "localhost", "port": 1883},
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
        kpm33b_meters={
            "upload_frequency_seconds": 5,
            "upload_frequency_minutes": 1,
            "exclude_device_ids": ["33BFAKE000000", "000000000000"],
        },
    )


@pytest.fixture
def bridge(config):
    with patch("src.bridge.mqtt.Client", side_effect=lambda **kw: MagicMock()):
        b = MqttBridge(config)
    return b


@pytest.fixture
def bridge_with_exclusion(config_with_exclusion):
    with patch("src.bridge.mqtt.Client", side_effect=lambda **kw: MagicMock()):
        b = MqttBridge(config_with_exclusion)
    return b


class TestOnInternalConnect:
    def test_subscribes_to_both_topics(self, bridge):
        mock_client = MagicMock()
        bridge._on_internal_connect(mock_client, None, {}, 0)
        calls = [c.args[0] for c in mock_client.subscribe.call_args_list]
        assert "MQTT_RT_DATA" in calls
        assert "MQTT_ENY_NOW" in calls

    def test_connection_failure_logs_error(self, bridge):
        mock_client = MagicMock()
        bridge._on_internal_connect(mock_client, None, {}, 5)
        mock_client.subscribe.assert_not_called()


class TestOnInternalMessage:
    def _make_msg(self, topic: str, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_rt_data_publishes_to_central(self, bridge):
        payload = {
            "id": "33B1225950027", "time": "20260112163900",
            "zyggl": 6.6905, "isend": "1",
        }
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg)

        # First message triggers HA discovery (2 calls) + data publish (1 call)
        assert bridge.central_client.publish.call_count == 3
        # Data publish is the last call
        data_call = bridge.central_client.publish.call_args_list[-1]
        assert data_call.args[0] == "kpm33b/33B1225950027/seconds"
        published = json.loads(data_call.args[1])
        assert published["active_power"] == 6.6905

    def test_eny_now_publishes_to_central(self, bridge):
        payload = {
            "id": "33B1225950027", "time": "20260117211500",
            "zygsz": 163.486, "isend": "1",
        }
        msg = self._make_msg("MQTT_ENY_NOW", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg)

        # Data publish is the last call (discovery may also fire)
        data_call = bridge.central_client.publish.call_args_list[-1]
        assert data_call.args[0] == "kpm33b/33B1225950027/minutes"
        published = json.loads(data_call.args[1])
        assert published["active_energy"] == 163.486

    def test_invalid_json_does_not_crash(self, bridge):
        msg = MagicMock()
        msg.topic = "MQTT_RT_DATA"
        msg.payload = b"not json{"
        bridge._on_internal_message(None, None, msg)
        # No exception raised

    def test_isend_error_does_not_publish(self, bridge):
        payload = {"id": "33B1225950027", "time": "20260112163900", "zyggl": 6.0, "isend": "0"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_unhandled_topic_ignored(self, bridge):
        payload = {"id": "33B1225950027", "isend": "1"}
        msg = self._make_msg("MQTT_OTHER", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_ha_discovery_published_on_first_message(self, bridge):
        """HA autodiscovery messages should be published for new meters."""
        payload = {"id": "33B1225950027", "time": "20260112163900", "zyggl": 6.0, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg)

        # Should publish 2 discovery configs + 1 data message
        assert bridge.central_client.publish.call_count == 3
        topics = [c.args[0] for c in bridge.central_client.publish.call_args_list]
        assert "homeassistant/sensor/kpm33b_33B1225950027/power/config" in topics
        assert "homeassistant/sensor/kpm33b_33B1225950027/energy/config" in topics

    def test_ha_discovery_not_repeated(self, bridge):
        """HA autodiscovery should only be published once per meter."""
        payload = {"id": "33B1225950027", "time": "20260112163900", "zyggl": 6.0, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        # First message — triggers discovery
        bridge._on_internal_message(None, None, msg)
        first_count = bridge.central_client.publish.call_count

        # Second message — no discovery
        bridge._on_internal_message(None, None, msg)
        second_count = bridge.central_client.publish.call_count

        # First: 2 discovery + 1 data = 3; Second: only 1 data
        assert first_count == 3
        assert second_count == 4  # 3 + 1 more data publish


class TestDeviceIdExclusion:
    def _make_msg(self, topic: str, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_excluded_device_ignored(self, bridge_with_exclusion):
        """Messages from excluded devices are ignored."""
        payload = {"id": "33BFAKE000000", "time": "20260112163900", "zyggl": 6.0, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge_with_exclusion.central_client.publish = MagicMock()

        bridge_with_exclusion._on_internal_message(None, None, msg)

        bridge_with_exclusion.central_client.publish.assert_not_called()

    def test_non_excluded_device_publishes(self, bridge_with_exclusion):
        """Messages from devices not in the exclusion list are published."""
        payload = {"id": "33B1225950027", "time": "20260112163900", "zyggl": 6.0, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge_with_exclusion.central_client.publish = MagicMock()
        bridge_with_exclusion.central_client.publish.return_value = MagicMock(rc=0)

        bridge_with_exclusion._on_internal_message(None, None, msg)

        # Should publish (discovery + data)
        assert bridge_with_exclusion.central_client.publish.call_count >= 1

    def test_no_exclusion_allows_all(self, bridge):
        """When exclude_device_ids is None, all devices are allowed."""
        payload = {"id": "33BFAKE000000", "time": "20260112163900", "zyggl": 6.0, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg)

        # Should publish even for "fake" device when no exclusion list
        assert bridge.central_client.publish.call_count >= 1


class TestStartStop:
    def test_start_calls_loop_start(self, bridge):
        bridge.start()
        bridge.internal_client.loop_start.assert_called_once()
        bridge.central_client.loop_start.assert_called_once()

    def test_stop_calls_loop_stop_and_disconnect(self, bridge):
        bridge.stop()
        bridge.internal_client.loop_stop.assert_called_once()
        bridge.central_client.loop_stop.assert_called_once()
        bridge.internal_client.disconnect.assert_called_once()
        bridge.central_client.disconnect.assert_called_once()
