"""Unit tests for src/rfbridge/ha_discovery.py."""

from unittest.mock import MagicMock

import paho.mqtt.client as mqtt

from src.rfbridge.ha_discovery import (
    clear_discovery,
    discovery_topic,
    make_battery_low_discovery_payload,
    make_humidity_discovery_payload,
    make_temperature_discovery_payload,
    publish_discovery,
)
from src.rfbridge.utils import sanitise_topic_name

OUTPUT_PREFIX = "tele/433rfbridge"
SENSOR_NAME = "living_room"
PROTOCOL = "nexus_compatible"
CHANNEL = 1
STATE_TOPIC = f"{OUTPUT_PREFIX}/{SENSOR_NAME}/state"
STABLE_ID = f"433rfbridge_{PROTOCOL}_ch{CHANNEL}"


class TestDiscoveryPayloads:
    def test_temperature_state_topic(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert payload["state_topic"] == STATE_TOPIC

    def test_temperature_unique_id_is_stable(self):
        # unique_id must NOT contain the friendly name — it must survive renames
        payload = make_temperature_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert payload["unique_id"] == f"{STABLE_ID}_temperature"
        assert SENSOR_NAME not in payload["unique_id"]

    def test_temperature_device_class(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert payload["device_class"] == "temperature"

    def test_humidity_unit(self):
        payload = make_humidity_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert payload["unit_of_measurement"] == "%"

    def test_battery_low_device_class(self):
        payload = make_battery_low_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert payload["device_class"] == "battery"

    def test_battery_low_value_template(self):
        payload = make_battery_low_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert "battery_low" in payload["value_template"]

    def test_device_block_uses_stable_identifier(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert STABLE_ID in payload["device"]["identifiers"]
        assert SENSOR_NAME not in payload["device"]["identifiers"]

    def test_rename_changes_state_topic_not_unique_id(self):
        p1 = make_temperature_discovery_payload("living_room", PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        p2 = make_temperature_discovery_payload("wohnzimmer", PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert p1["unique_id"] == p2["unique_id"]
        assert p1["state_topic"] != p2["state_topic"]


class TestDiscoveryTopic:
    def test_temperature_topic(self):
        topic = discovery_topic(SENSOR_NAME, "temperature")
        assert topic == f"homeassistant/sensor/433rfbridge_{SENSOR_NAME}_temperature/config"

    def test_humidity_topic(self):
        topic = discovery_topic(SENSOR_NAME, "humidity")
        assert topic == f"homeassistant/sensor/433rfbridge_{SENSOR_NAME}_humidity/config"

    def test_battery_low_uses_binary_sensor_component(self):
        topic = discovery_topic(SENSOR_NAME, "battery_low")
        assert topic == f"homeassistant/binary_sensor/433rfbridge_{SENSOR_NAME}_battery_low/config"


class TestPublishDiscovery:
    def test_publishes_three_entities(self):
        # 3 entity payloads + 1 stale-clear for old sensor/battery_low topic
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
        publish_discovery(client, SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert client.publish.call_count == 4

    def test_publishes_with_retain(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
        publish_discovery(client, SENSOR_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        for c in client.publish.call_args_list:
            assert c.kwargs.get("retain") is True


class TestClearDiscovery:
    def test_clears_all_three_entity_topics(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
        clear_discovery(client, SENSOR_NAME)
        assert client.publish.call_count == 3
        topics = [c.args[0] for c in client.publish.call_args_list]
        assert any("temperature" in t for t in topics)
        assert any("humidity" in t for t in topics)
        assert any("battery_low" in t for t in topics)


class TestSanitisedTopicNames:
    """Verify that spaces and umlauts in friendly names are normalised in all topic paths."""

    RAW_NAME = "EG Wohnküche"
    SAFE_NAME = "EG_Wohnkueche"

    def test_state_topic_uses_sanitised_name(self):
        payload = make_temperature_discovery_payload(self.RAW_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert payload["state_topic"] == f"{OUTPUT_PREFIX}/{self.SAFE_NAME}/state"

    def test_state_topic_no_raw_chars(self):
        payload = make_temperature_discovery_payload(self.RAW_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        assert " " not in payload["state_topic"]
        assert "ü" not in payload["state_topic"]

    def test_discovery_topic_uses_sanitised_name(self):
        topic = discovery_topic(self.RAW_NAME, "temperature")
        assert self.SAFE_NAME in topic
        assert " " not in topic
        assert "ü" not in topic

    def test_clear_discovery_uses_sanitised_name(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
        clear_discovery(client, self.RAW_NAME)
        topics = [c.args[0] for c in client.publish.call_args_list]
        for t in topics:
            assert " " not in t, f"Space found in topic: {t}"
            assert "ü" not in t, f"Umlaut found in topic: {t}"
        assert any(self.SAFE_NAME in t for t in topics)

    def test_state_topic_matches_between_discovery_and_bridge_publish(self):
        # The topic bridge.py will publish to must match ha_discovery.py's state_topic.
        payload = make_temperature_discovery_payload(self.RAW_NAME, PROTOCOL, CHANNEL, OUTPUT_PREFIX)
        expected_state_topic = f"{OUTPUT_PREFIX}/{sanitise_topic_name(self.RAW_NAME)}/state"
        assert payload["state_topic"] == expected_state_topic
