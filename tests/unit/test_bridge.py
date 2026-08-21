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
def config_with_contexts():
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
            "device_contexts": {
                "33B1225950027": "building1/floor2",
                "33B1225950028": "building2",
            },
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


@pytest.fixture
def bridge_with_contexts(config_with_contexts):
    with patch("src.bridge.mqtt.Client", side_effect=lambda **kw: MagicMock()):
        b = MqttBridge(config_with_contexts)
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

        # Data publish is the last call (HA discovery fires first)
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

        calls = bridge.central_client.publish.call_args_list
        config_topics = [c.args[0] for c in calls if c.args[0].startswith("homeassistant/") and c.args[1]]
        assert config_topics == [
            "homeassistant/sensor/kpm33b_33B1225950027/power/config",
            "homeassistant/sensor/kpm33b_33B1225950027/energy/config",
        ]
        assert calls[-1].args[0] == "kpm33b/33B1225950027/seconds"

    def test_ha_discovery_not_repeated(self, bridge):
        """HA autodiscovery should only be published once per meter."""
        payload1 = {"id": "33B1225950027", "time": "20260112163900", "zyggl": 6.0, "isend": "1"}
        payload2 = {"id": "33B1225950027", "time": "20260112164000", "zyggl": 7.0, "isend": "1"}
        msg1 = self._make_msg("MQTT_RT_DATA", payload1)
        msg2 = self._make_msg("MQTT_RT_DATA", payload2)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        # First message — triggers discovery
        bridge._on_internal_message(None, None, msg1)
        first_count = bridge.central_client.publish.call_count

        # Second message with different timestamp — no discovery, only the data publish
        bridge._on_internal_message(None, None, msg2)
        second_count = bridge.central_client.publish.call_count

        assert second_count == first_count + 1
        assert bridge.central_client.publish.call_args_list[-1].args[0] == "kpm33b/33B1225950027/seconds"


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


class TestDeviceContext:
    """Tests for device context (location/function) in MQTT topics."""

    def _make_msg(self, topic: str, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_get_device_context_returns_context(self, bridge_with_contexts):
        context = bridge_with_contexts._get_device_context("33B1225950027")
        assert context == "building1/floor2"

    def test_get_device_context_returns_none_for_unknown(self, bridge_with_contexts):
        context = bridge_with_contexts._get_device_context("33BUNKNOWN000")
        assert context is None

    def test_get_device_context_returns_none_when_no_contexts(self, bridge):
        context = bridge._get_device_context("33B1225950027")
        assert context is None

    def test_build_topic_prefix_with_context(self, bridge_with_contexts):
        prefix = bridge_with_contexts._build_topic_prefix("33B1225950027")
        assert prefix == "kpm33b/building1/floor2/33B1225950027"

    def test_build_topic_prefix_without_context(self, bridge_with_contexts):
        prefix = bridge_with_contexts._build_topic_prefix("33BUNKNOWN000")
        assert prefix == "kpm33b/33BUNKNOWN000"

    def test_build_topic_prefix_no_contexts_config(self, bridge):
        prefix = bridge._build_topic_prefix("33B1225950027")
        assert prefix == "kpm33b/33B1225950027"

    def test_rt_data_publishes_with_context(self, bridge_with_contexts):
        payload = {
            "id": "33B1225950027", "time": "20260112163900",
            "zyggl": 6.6905, "isend": "1",
        }
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge_with_contexts.central_client.publish = MagicMock()
        bridge_with_contexts.central_client.publish.return_value = MagicMock(rc=0)

        bridge_with_contexts._on_internal_message(None, None, msg)

        # Data publish is the last call
        data_call = bridge_with_contexts.central_client.publish.call_args_list[-1]
        assert data_call.args[0] == "kpm33b/building1/floor2/33B1225950027/seconds"

    def test_eny_now_publishes_with_context(self, bridge_with_contexts):
        payload = {
            "id": "33B1225950028", "time": "20260117211500",
            "zygsz": 163.486, "isend": "1",
        }
        msg = self._make_msg("MQTT_ENY_NOW", payload)
        bridge_with_contexts.central_client.publish = MagicMock()
        bridge_with_contexts.central_client.publish.return_value = MagicMock(rc=0)

        bridge_with_contexts._on_internal_message(None, None, msg)

        # Data publish is the last call
        data_call = bridge_with_contexts.central_client.publish.call_args_list[-1]
        assert data_call.args[0] == "kpm33b/building2/33B1225950028/minutes"

    def test_device_without_context_uses_direct_topic(self, bridge_with_contexts):
        """Device not in device_contexts map should use direct topic format."""
        payload = {
            "id": "33BUNKNOWN000", "time": "20260112163900",
            "zyggl": 1.0, "isend": "1",
        }
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge_with_contexts.central_client.publish = MagicMock()
        bridge_with_contexts.central_client.publish.return_value = MagicMock(rc=0)

        bridge_with_contexts._on_internal_message(None, None, msg)

        data_call = bridge_with_contexts.central_client.publish.call_args_list[-1]
        assert data_call.args[0] == "kpm33b/33BUNKNOWN000/seconds"

    def test_ha_discovery_includes_context(self, bridge_with_contexts):
        """HA discovery state_topic should include context if configured."""
        payload = {
            "id": "33B1225950027", "time": "20260112163900",
            "zyggl": 6.0, "isend": "1",
        }
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge_with_contexts.central_client.publish = MagicMock()
        bridge_with_contexts.central_client.publish.return_value = MagicMock(rc=0)

        bridge_with_contexts._on_internal_message(None, None, msg)

        # Find the power discovery call
        for call in bridge_with_contexts.central_client.publish.call_args_list:
            if "power/config" in call.args[0]:
                discovery_payload = json.loads(call.args[1])
                assert discovery_payload["state_topic"] == "kpm33b/building1/floor2/33B1225950027/seconds"
                break
        else:
            pytest.fail("Power discovery message not found")


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


class TestZeroValueFiltering:
    """Tests for zero-value message filtering (KPM33B bug workaround)."""

    def _make_msg(self, topic: str, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_zero_value_message_dropped(self, bridge):
        """Message with all zero data values should be filtered out."""
        payload = {"id": "33B1225950029", "time": "20260218103000", "zyggl": 0, "zygsz": 0.0, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_zero_value_string_dropped(self, bridge):
        """Message with '0' string values should also be filtered."""
        payload = {"id": "33B1225950029", "time": "20260218103000", "zyggl": "0", "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_empty_string_value_dropped(self, bridge):
        """Message with empty string data values should be filtered."""
        payload = {"id": "33B1225950029", "time": "20260218103000", "zyggl": "", "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_none_value_dropped(self, bridge):
        """Message with None data values should be filtered."""
        payload = {"id": "33B1225950029", "time": "20260218103000", "zyggl": None, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_nonzero_value_passes(self, bridge):
        """Message with non-zero data value should be published."""
        payload = {"id": "33B1225950027", "time": "20260218103000", "zyggl": 6.6905, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg)

        # Should publish (discovery + data)
        assert bridge.central_client.publish.call_count >= 1

    def test_only_metadata_values_still_filtered(self, bridge):
        """Message with only id, time, isend (no data keys) should be filtered."""
        payload = {"id": "33B1225950029", "time": "20260218103000", "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()

        bridge._on_internal_message(None, None, msg)

        bridge.central_client.publish.assert_not_called()

    def test_is_zero_value_message_true_for_all_zeros(self, bridge):
        """_is_zero_value_message returns True when all data values are zero."""
        raw = {"id": "33B1225950029", "time": "20260218103000", "zyggl": 0, "zygsz": 0.0, "isend": "1"}
        assert bridge._is_zero_value_message(raw) is True

    def test_is_zero_value_message_false_for_nonzero(self, bridge):
        """_is_zero_value_message returns False when a data value is non-zero."""
        raw = {"id": "33B1225950029", "time": "20260218103000", "zyggl": 5.5, "isend": "1"}
        assert bridge._is_zero_value_message(raw) is False


class TestDuplicateFiltering:
    """Tests for duplicate message filtering."""

    def _make_msg(self, topic: str, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_duplicate_message_dropped(self, bridge):
        """Second message with same id+timestamp should be filtered."""
        payload = {"id": "33B1225950028", "time": "20260218103000", "zyggl": 53.828, "isend": "1"}
        msg = self._make_msg("MQTT_RT_DATA", payload)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        # First message
        bridge._on_internal_message(None, None, msg)
        first_count = bridge.central_client.publish.call_count

        # Second identical message (duplicate)
        bridge._on_internal_message(None, None, msg)
        second_count = bridge.central_client.publish.call_count

        assert first_count >= 1  # First message published
        assert second_count == first_count  # Duplicate filtered

    def test_different_timestamp_passes(self, bridge):
        """Messages with same id but different timestamps should both pass."""
        payload1 = {"id": "33B1225950028", "time": "20260218103000", "zyggl": 53.828, "isend": "1"}
        payload2 = {"id": "33B1225950028", "time": "20260218103100", "zyggl": 54.0, "isend": "1"}
        msg1 = self._make_msg("MQTT_RT_DATA", payload1)
        msg2 = self._make_msg("MQTT_RT_DATA", payload2)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg1)
        first_count = bridge.central_client.publish.call_count

        bridge._on_internal_message(None, None, msg2)
        second_count = bridge.central_client.publish.call_count

        # Second message has different timestamp, so it should be published
        assert second_count > first_count

    def test_different_device_id_passes(self, bridge):
        """Messages with same timestamp but different device IDs should both pass."""
        payload1 = {"id": "33B1225950027", "time": "20260218103000", "zyggl": 10.0, "isend": "1"}
        payload2 = {"id": "33B1225950028", "time": "20260218103000", "zyggl": 20.0, "isend": "1"}
        msg1 = self._make_msg("MQTT_RT_DATA", payload1)
        msg2 = self._make_msg("MQTT_RT_DATA", payload2)
        bridge.central_client.publish = MagicMock()
        bridge.central_client.publish.return_value = MagicMock(rc=0)

        bridge._on_internal_message(None, None, msg1)
        first_count = bridge.central_client.publish.call_count

        bridge._on_internal_message(None, None, msg2)
        second_count = bridge.central_client.publish.call_count

        # Second message has different device ID, so it should be published
        assert second_count > first_count

    def test_is_duplicate_returns_true_for_seen(self, bridge):
        """_is_duplicate_message returns True for previously seen id+timestamp."""
        bridge._is_duplicate_message("33B1225950028", "20260218103000")
        assert bridge._is_duplicate_message("33B1225950028", "20260218103000") is True

    def test_is_duplicate_returns_false_for_new(self, bridge):
        """_is_duplicate_message returns False for new id+timestamp."""
        assert bridge._is_duplicate_message("33B1225950028", "20260218103000") is False

    def test_seen_messages_dict_bounded(self, bridge):
        """_seen_messages dict should not exceed duplicate_dict_max_length."""
        max_length = bridge.config.kpm33b_meters.duplicate_dict_max_length
        # Add more messages than the limit
        for i in range(max_length + 10):
            bridge._is_duplicate_message(f"33B12259500{i:02d}", f"202602181030{i:02d}")

        assert len(bridge._seen_messages) <= max_length

    def test_oldest_entries_evicted_first(self, bridge):
        """Oldest entries should be evicted when limit exceeded."""
        bridge.config.kpm33b_meters.duplicate_dict_max_length = 5
        bridge._seen_messages.clear()

        # Add 5 messages
        for i in range(5):
            bridge._is_duplicate_message(f"DEV{i}", f"TIME{i}")

        # Add one more
        bridge._is_duplicate_message("DEV5", "TIME5")

        # First entry should be evicted
        assert "DEV0_TIME0" not in bridge._seen_messages
        # Last entry should remain
        assert "DEV5_TIME5" in bridge._seen_messages


class TestPerPhaseForwarding:
    """Per-phase payload extension per issue #12."""

    RT_PAYLOAD = {
        "id": "33B1225950027", "time": "20260112163900",
        "ia": 9.735, "ib": 9.658, "ic": 9.655,
        "ua": 229.097, "ub": 231.567, "uc": 232.529,
        "pa": 2.2229, "pb": 2.2293, "pc": 2.2382,
        "zyggl": 6.6905, "zglys": 0.996, "isend": "1",
    }

    def _make_msg(self, topic: str, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def _bridge(self, per_phase_device_ids: list[str], config: AppConfig) -> MqttBridge:
        config.kpm33b_meters.per_phase_device_ids = per_phase_device_ids
        with patch("src.bridge.mqtt.Client", side_effect=lambda **kw: MagicMock()):
            bridge = MqttBridge(config)
        bridge.central_client.publish = MagicMock(return_value=MagicMock(rc=0))
        return bridge

    def test_enabled_meter_gets_per_phase_fields(self, config):
        bridge = self._bridge(["33B1225950027"], config)
        bridge._on_internal_message(None, None, self._make_msg("MQTT_RT_DATA", self.RT_PAYLOAD))

        published = json.loads(bridge.central_client.publish.call_args_list[-1].args[1])
        assert published["active_power"] == 6.6905
        assert published["current_l1"] == 9.735
        assert published["active_power_l2"] == 2.2293
        assert published["voltage_l3"] == 232.529

    def test_disabled_meter_payload_unchanged(self, config):
        bridge = self._bridge(["33B1225950029"], config)
        bridge._on_internal_message(None, None, self._make_msg("MQTT_RT_DATA", self.RT_PAYLOAD))

        published = json.loads(bridge.central_client.publish.call_args_list[-1].args[1])
        assert set(published.keys()) == {"id", "time", "active_power"}

    def test_enabled_meter_gets_per_phase_discovery(self, config):
        bridge = self._bridge(["33B1225950027"], config)
        bridge._on_internal_message(None, None, self._make_msg("MQTT_RT_DATA", self.RT_PAYLOAD))

        configs = {
            c.args[0]: c.args[1]
            for c in bridge.central_client.publish.call_args_list
            if c.args[0].startswith("homeassistant/") and c.args[1]
        }
        assert "homeassistant/sensor/kpm33b_33B1225950027/current_l1/config" in configs
        assert "homeassistant/sensor/kpm33b_33B1225950027/power_factor/config" not in configs

    def test_expire_after_uses_per_device_frequency(self, config):
        config.kpm33b_meters.upload_frequency_seconds_by_device = {"33B1225950027": 30}
        bridge = self._bridge([], config)
        bridge._on_internal_message(None, None, self._make_msg("MQTT_RT_DATA", self.RT_PAYLOAD))

        power_config = next(
            json.loads(c.args[1])
            for c in bridge.central_client.publish.call_args_list
            if c.args[0].endswith("/power/config")
        )
        assert power_config["expire_after"] == 75
