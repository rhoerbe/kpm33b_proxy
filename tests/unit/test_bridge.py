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
            "meter_settime_ack": "MQTT_COMMOD_READ_REP",
        },
        central_broker_topics={
            "external_main_topic": "kpm33b",
            "status_topic": "kpm33b/status",
        },
        logging={"level": "DEBUG", "file": "/tmp/test.log"},
        kpm33b_meters={"upload_frequency_seconds": 5, "upload_frequency_minutes": 1},
    )


@pytest.fixture
def bridge(config):
    with patch("src.bridge.mqtt.Client", side_effect=lambda **kw: MagicMock()):
        b = MqttBridge(config)
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

        bridge.central_client.publish.assert_called_once()
        call_args = bridge.central_client.publish.call_args
        assert call_args.args[0] == "kpm33b/33B1225950027/seconds"
        published = json.loads(call_args.args[1])
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

        call_args = bridge.central_client.publish.call_args
        assert call_args.args[0] == "kpm33b/33B1225950027/minutes"
        published = json.loads(call_args.args[1])
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
