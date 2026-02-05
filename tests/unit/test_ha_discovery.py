"""Unit tests for src/ha_discovery.py."""

import json
from unittest.mock import MagicMock

import pytest

from src.ha_discovery import (
    DISCOVERY_PREFIX,
    MANUFACTURER,
    MODEL,
    discovery_topic,
    make_energy_discovery_payload,
    make_power_discovery_payload,
    publish_discovery,
)


METER_ID = "33B1225950027"
BASE_TOPIC = "kpm33b"


class TestPowerDiscoveryPayload:
    def test_required_fields(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        assert payload["name"] == "Active Power"
        assert payload["unique_id"] == f"kpm33b_{METER_ID}_power"
        assert payload["state_topic"] == f"{BASE_TOPIC}/{METER_ID}/seconds"
        assert payload["device_class"] == "power"
        assert payload["state_class"] == "measurement"
        assert payload["unit_of_measurement"] == "kW"
        assert payload["value_template"] == "{{ value_json.active_power }}"

    def test_device_block(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        device = payload["device"]
        assert device["identifiers"] == [f"kpm33b_{METER_ID}"]
        assert device["name"] == f"KPM33B {METER_ID}"
        assert device["manufacturer"] == MANUFACTURER
        assert device["model"] == MODEL

    def test_json_serializable(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        json_str = json.dumps(payload)
        assert isinstance(json_str, str)
        assert METER_ID in json_str


class TestEnergyDiscoveryPayload:
    def test_required_fields(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        assert payload["name"] == "Active Energy"
        assert payload["unique_id"] == f"kpm33b_{METER_ID}_energy"
        assert payload["state_topic"] == f"{BASE_TOPIC}/{METER_ID}/minutes"
        assert payload["device_class"] == "energy"
        assert payload["state_class"] == "total_increasing"
        assert payload["unit_of_measurement"] == "kWh"
        assert payload["value_template"] == "{{ value_json.active_energy }}"

    def test_device_block(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        device = payload["device"]
        assert device["identifiers"] == [f"kpm33b_{METER_ID}"]
        assert device["name"] == f"KPM33B {METER_ID}"
        assert device["manufacturer"] == MANUFACTURER
        assert device["model"] == MODEL

    def test_json_serializable(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        json_str = json.dumps(payload)
        assert isinstance(json_str, str)
        assert METER_ID in json_str


class TestDiscoveryTopic:
    def test_power_topic(self):
        topic = discovery_topic(METER_ID, "power")
        assert topic == f"{DISCOVERY_PREFIX}/sensor/kpm33b_{METER_ID}/power/config"

    def test_energy_topic(self):
        topic = discovery_topic(METER_ID, "energy")
        assert topic == f"{DISCOVERY_PREFIX}/sensor/kpm33b_{METER_ID}/energy/config"

    def test_topic_format(self):
        topic = discovery_topic(METER_ID, "power")
        parts = topic.split("/")
        assert parts[0] == "homeassistant"
        assert parts[1] == "sensor"
        assert parts[2] == f"kpm33b_{METER_ID}"
        assert parts[3] == "power"
        assert parts[4] == "config"


class TestPublishDiscovery:
    def test_publishes_both_sensors(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=0)

        publish_discovery(client, METER_ID, BASE_TOPIC)

        assert client.publish.call_count == 2

    def test_power_publish_args(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=0)

        publish_discovery(client, METER_ID, BASE_TOPIC)

        power_call = client.publish.call_args_list[0]
        topic = power_call.args[0]
        payload = json.loads(power_call.args[1])

        assert topic == f"{DISCOVERY_PREFIX}/sensor/kpm33b_{METER_ID}/power/config"
        assert payload["device_class"] == "power"
        assert power_call.kwargs["qos"] == 1
        assert power_call.kwargs["retain"] is True

    def test_energy_publish_args(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=0)

        publish_discovery(client, METER_ID, BASE_TOPIC)

        energy_call = client.publish.call_args_list[1]
        topic = energy_call.args[0]
        payload = json.loads(energy_call.args[1])

        assert topic == f"{DISCOVERY_PREFIX}/sensor/kpm33b_{METER_ID}/energy/config"
        assert payload["device_class"] == "energy"
        assert energy_call.kwargs["qos"] == 1
        assert energy_call.kwargs["retain"] is True

    def test_shared_device_identifiers(self):
        """Both sensors should have same device identifiers so HA groups them."""
        power = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        energy = make_energy_discovery_payload(METER_ID, BASE_TOPIC)

        assert power["device"]["identifiers"] == energy["device"]["identifiers"]
        assert power["device"]["name"] == energy["device"]["name"]


class TestContextSupport:
    """Tests for optional context parameter in discovery payloads."""

    def test_power_payload_with_context(self):
        context = "building1/floor2"
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, context)
        assert payload["state_topic"] == f"{BASE_TOPIC}/{context}/{METER_ID}/seconds"

    def test_power_payload_without_context(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, None)
        assert payload["state_topic"] == f"{BASE_TOPIC}/{METER_ID}/seconds"

    def test_energy_payload_with_context(self):
        context = "building1/floor2"
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC, context)
        assert payload["state_topic"] == f"{BASE_TOPIC}/{context}/{METER_ID}/minutes"

    def test_energy_payload_without_context(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC, None)
        assert payload["state_topic"] == f"{BASE_TOPIC}/{METER_ID}/minutes"

    def test_publish_discovery_with_context(self):
        client = MagicMock()
        client.publish.return_value = MagicMock(rc=0)
        context = "building1/floor2"

        publish_discovery(client, METER_ID, BASE_TOPIC, context)

        power_call = client.publish.call_args_list[0]
        power_payload = json.loads(power_call.args[1])
        assert power_payload["state_topic"] == f"{BASE_TOPIC}/{context}/{METER_ID}/seconds"

        energy_call = client.publish.call_args_list[1]
        energy_payload = json.loads(energy_call.args[1])
        assert energy_payload["state_topic"] == f"{BASE_TOPIC}/{context}/{METER_ID}/minutes"

    def test_context_with_nested_path(self):
        context = "campus/building1/floor2/room101"
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, context)
        assert payload["state_topic"] == f"{BASE_TOPIC}/{context}/{METER_ID}/seconds"
