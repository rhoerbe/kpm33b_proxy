"""Unit tests for src/rfbridge/ha_discovery.py."""

from unittest.mock import MagicMock

import paho.mqtt.client as mqtt

from src.rfbridge.ha_discovery import (
    discovery_topic,
    make_battery_low_discovery_payload,
    make_humidity_discovery_payload,
    make_temperature_discovery_payload,
    publish_discovery,
)

OUTPUT_PREFIX = "tele/433rfbridge"
SENSOR_NAME = "living_room"
STATE_TOPIC = f"{OUTPUT_PREFIX}/{SENSOR_NAME}/state"


class TestDiscoveryPayloads:
    def test_temperature_state_topic(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert payload["state_topic"] == STATE_TOPIC

    def test_temperature_unique_id(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert payload["unique_id"] == "433rfbridge_living_room_temperature"

    def test_temperature_device_class(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert payload["device_class"] == "temperature"

    def test_humidity_unit(self):
        payload = make_humidity_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert payload["unit_of_measurement"] == "%"

    def test_battery_low_device_class(self):
        payload = make_battery_low_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert payload["device_class"] == "battery"

    def test_battery_low_value_template(self):
        payload = make_battery_low_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert "battery_low" in payload["value_template"]

    def test_device_block_identifiers(self):
        payload = make_temperature_discovery_payload(SENSOR_NAME, OUTPUT_PREFIX)
        assert f"433rfbridge_{SENSOR_NAME}" in payload["device"]["identifiers"]


class TestDiscoveryTopic:
    def test_temperature_topic(self):
        topic = discovery_topic(SENSOR_NAME, "temperature")
        assert topic == f"homeassistant/sensor/433rfbridge_{SENSOR_NAME}_temperature/config"

    def test_humidity_topic(self):
        topic = discovery_topic(SENSOR_NAME, "humidity")
        assert topic == f"homeassistant/sensor/433rfbridge_{SENSOR_NAME}_humidity/config"


class TestPublishDiscovery:
    def test_publishes_three_entities(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
        publish_discovery(client, SENSOR_NAME, OUTPUT_PREFIX)
        assert client.publish.call_count == 3

    def test_publishes_with_retain(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=mqtt.MQTT_ERR_SUCCESS)
        publish_discovery(client, SENSOR_NAME, OUTPUT_PREFIX)
        for call in client.publish.call_args_list:
            assert call.kwargs.get("retain") is True or (len(call.args) >= 4 and call.args[3] is True)
