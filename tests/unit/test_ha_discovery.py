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

    def test_context_used_as_device_name(self):
        """Context should be used as the HA device friendly name."""
        context = "Heatpump Power"
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, context)
        assert payload["device"]["name"] == "Heatpump Power"

    def test_no_context_uses_default_name(self):
        """Without context, device name defaults to KPM33B + meter_id."""
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, None)
        assert payload["device"]["name"] == f"KPM33B {METER_ID}"


class TestDisplayPrecision:
    """Tests for suggested_display_precision attribute."""

    def test_power_precision_is_zero(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        assert payload["suggested_display_precision"] == 0

    def test_energy_precision_is_zero(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        assert payload["suggested_display_precision"] == 0


class TestExpireAfter:
    """Tests for expire_after attribute (availability monitoring)."""

    def test_power_expire_after_default(self):
        """Power expire_after should be upload_frequency_seconds * 1.5."""
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        # Default is 30 seconds, so expire_after = 30 * 1.5 = 45
        assert payload["expire_after"] == 45

    def test_power_expire_after_custom_frequency(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=60)
        # 60 * 1.5 = 90
        assert payload["expire_after"] == 90

    def test_energy_expire_after_default(self):
        """Energy expire_after should be upload_frequency_minutes * 60 * 1.5."""
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        # Default is 1 minute, so expire_after = 1 * 60 * 1.5 = 90
        assert payload["expire_after"] == 90

    def test_energy_expire_after_custom_frequency(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=5)
        # 5 * 60 * 1.5 = 450
        assert payload["expire_after"] == 450


class TestManufacturer:
    """Tests for manufacturer string."""

    def test_manufacturer_is_compere_power(self):
        assert MANUFACTURER == "compere-power.com"

    def test_power_device_has_correct_manufacturer(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        assert payload["device"]["manufacturer"] == "compere-power.com"

    def test_energy_device_has_correct_manufacturer(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        assert payload["device"]["manufacturer"] == "compere-power.com"
