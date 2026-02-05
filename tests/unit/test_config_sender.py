"""Unit tests for src/config_sender.py."""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.config import AppConfig
from src.config_sender import ACK_TIMEOUT, ConfigSender, _make_oprid, _meter_id_last8


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
def sender(config):
    with patch("src.config_sender.mqtt.Client", side_effect=lambda **kw: MagicMock()):
        s = ConfigSender(config)
    s.internal_client.publish = MagicMock(return_value=MagicMock(rc=0))
    return s


class TestHelpers:
    def test_make_oprid_length(self):
        oprid = _make_oprid()
        assert len(oprid) == 32
        assert oprid.isalnum()

    def test_make_oprid_unique(self):
        assert _make_oprid() != _make_oprid()

    def test_meter_id_last8(self):
        assert _meter_id_last8("33B1225950027") == "25950027"


class TestMeterDiscovery:
    def test_new_meter_discovered(self, sender):
        msg = MagicMock()
        msg.topic = "kpm33b/33B1225950027/seconds"
        msg.payload = b'{"id":"33B1225950027","time":"20260112163900","active_power":6.6905}'

        with patch.object(sender, "_send_config_to_meter") as mock_send:
            sender._on_central_message(None, None, msg)

        assert "33B1225950027" in sender.known_meters
        mock_send.assert_called_once_with("33B1225950027")

    def test_duplicate_meter_not_resent(self, sender):
        sender.known_meters.add("33B1225950027")
        msg = MagicMock()
        msg.topic = "kpm33b/33B1225950027/seconds"
        msg.payload = b'{}'

        with patch.object(sender, "_send_config_to_meter") as mock_send:
            sender._on_central_message(None, None, msg)

        mock_send.assert_not_called()

    def test_short_topic_ignored(self, sender):
        msg = MagicMock()
        msg.topic = "kpm33b"
        msg.payload = b'{}'

        with patch.object(sender, "_send_config_to_meter") as mock_send:
            sender._on_central_message(None, None, msg)

        mock_send.assert_not_called()


class TestCentralConnect:
    def test_subscribes_to_discovery_topic(self, sender):
        mock_client = MagicMock()
        sender._on_central_connect(mock_client, None, {}, 0)
        mock_client.subscribe.assert_called_once_with("kpm33b/+/seconds")

    def test_connection_failure(self, sender):
        mock_client = MagicMock()
        sender._on_central_connect(mock_client, None, {}, 5)
        mock_client.subscribe.assert_not_called()


class TestInternalConnect:
    def test_subscribes_to_ack_topic(self, sender):
        mock_client = MagicMock()
        sender._on_internal_connect(mock_client, None, {}, 0)
        mock_client.subscribe.assert_called_once_with("MQTT_COMMOD_SET_REP")


class TestSendConfig:
    def test_sends_two_commands(self, sender):
        sender._send_config_to_meter("33B1225950027")
        assert sender.internal_client.publish.call_count == 2

    def test_seconds_command_payload(self, sender):
        sender._send_config_to_meter("33B1225950027")
        first_call = sender.internal_client.publish.call_args_list[0]
        topic = first_call.args[0]
        payload = json.loads(first_call.args[1])
        assert topic == "MQTT_COMMOD_SET_25950027"
        assert payload["Cmd"] == "0000"
        assert payload["value"] == "5"
        assert payload["types"] == "1"
        assert len(payload["oprid"]) == 32

    def test_minutes_command_payload(self, sender):
        sender._send_config_to_meter("33B1225950027")
        second_call = sender.internal_client.publish.call_args_list[1]
        payload = json.loads(second_call.args[1])
        assert payload["Cmd"] == "0001"
        assert payload["value"] == "1"


class TestAckHandling:
    def test_ack_received_clears_pending(self, sender):
        event = threading.Event()
        sender._pending_acks["abc123"] = event
        msg = MagicMock()
        msg.topic = "MQTT_COMMOD_SET_REP"
        msg.payload = json.dumps({"oprid": "abc123"}).encode()

        sender._on_internal_message(None, None, msg)

        assert event.is_set()
        assert "abc123" not in sender._pending_acks

    def test_unknown_oprid_ignored(self, sender):
        msg = MagicMock()
        msg.topic = "MQTT_COMMOD_SET_REP"
        msg.payload = json.dumps({"oprid": "unknown"}).encode()
        sender._on_internal_message(None, None, msg)
        # No error raised

    def test_invalid_json_ack(self, sender):
        msg = MagicMock()
        msg.topic = "MQTT_COMMOD_SET_REP"
        msg.payload = b"not json"
        sender._on_internal_message(None, None, msg)
        # No error raised

    def test_ack_missing_oprid(self, sender):
        msg = MagicMock()
        msg.topic = "MQTT_COMMOD_SET_REP"
        msg.payload = json.dumps({"something": "else"}).encode()
        sender._on_internal_message(None, None, msg)
        # No error raised


class TestConfigMtimeMonitoring:
    def test_first_check_records_mtime(self, sender, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("test: true")
        sender._config_path = cfg_file
        sender._config_mtime = 0.0

        sender._check_config_mtime()

        assert sender._config_mtime > 0.0

    def test_unchanged_file_no_resend(self, sender, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("test: true")
        sender._config_path = cfg_file
        sender._config_mtime = cfg_file.stat().st_mtime
        sender.known_meters = {"33B1225950027"}

        with patch.object(sender, "_send_config_to_meter") as mock_send:
            sender._check_config_mtime()

        mock_send.assert_not_called()

    def test_changed_file_triggers_resend(self, sender, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("test: true")
        sender._config_path = cfg_file
        sender._config_mtime = cfg_file.stat().st_mtime - 10  # simulate older mtime
        sender.known_meters = {"33B1225950027", "33B1225950028"}

        with patch.object(sender, "_send_config_to_meter") as mock_send:
            sender._check_config_mtime()

        assert mock_send.call_count == 2

    def test_missing_config_file_no_error(self, sender, tmp_path):
        sender._config_path = tmp_path / "nonexistent.yaml"
        sender._check_config_mtime()
        # No error raised


class TestStartStop:
    def test_start_calls_loop_start(self, sender):
        sender.start()
        sender.central_client.loop_start.assert_called_once()
        sender.internal_client.loop_start.assert_called_once()
        sender._stop_event.set()  # stop the monitor thread

    def test_stop_disconnects(self, sender):
        sender.stop()
        sender.central_client.loop_stop.assert_called_once()
        sender.internal_client.loop_stop.assert_called_once()
        sender.central_client.disconnect.assert_called_once()
        sender.internal_client.disconnect.assert_called_once()
