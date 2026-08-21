"""Unit tests for src/ha_discovery.py."""

import json
from unittest.mock import MagicMock

import pytest

from src.ha_discovery import (
    DISCOVERY_PREFIX,
    EXPIRE_AFTER_FACTOR,
    MANUFACTURER,
    MODEL,
    all_per_phase_fields,
    discovery_topic,
    make_energy_discovery_payload,
    make_phase_discovery_payload,
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

        config_topics = {call.args[0] for call in client.publish.call_args_list if call.args[1]}
        assert config_topics == {discovery_topic(METER_ID, "power"), discovery_topic(METER_ID, "energy")}

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
        """Power expire_after should be upload_frequency_seconds * EXPIRE_AFTER_FACTOR."""
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC)
        # Default is 30 seconds, so expire_after = 30 * 2.5 = 75
        assert payload["expire_after"] == 75

    def test_power_expire_after_custom_frequency(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=60)
        # 60 * 2.5 = 150
        assert payload["expire_after"] == 150

    def test_power_expire_after_exceeds_publish_interval(self):
        """Regression (issue #12): expire_after must never be shorter than the publish interval."""
        for frequency in (30, 60, 300):
            payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=frequency)
            assert payload["expire_after"] > frequency

    def test_default_factor_tolerates_a_missed_publish(self):
        assert EXPIRE_AFTER_FACTOR > 2.0

    def test_power_expire_after_custom_factor(self):
        payload = make_power_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=30, expire_after_factor=4.0)
        assert payload["expire_after"] == 120

    def test_energy_expire_after_default(self):
        """Energy expire_after should be upload_frequency_minutes * 60 * EXPIRE_AFTER_FACTOR."""
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC)
        # Default is 1 minute, so expire_after = 1 * 60 * 2.5 = 150
        assert payload["expire_after"] == 150

    def test_energy_expire_after_custom_frequency(self):
        payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=5)
        # 5 * 60 * 2.5 = 750
        assert payload["expire_after"] == 750

    def test_energy_expire_after_exceeds_publish_interval(self):
        for minutes in (1, 5, 15):
            payload = make_energy_discovery_payload(METER_ID, BASE_TOPIC, upload_frequency=minutes)
            assert payload["expire_after"] > minutes * 60


class TestPerPhaseDiscoveryPayload:
    """Tests for the per-phase sensors added in issue #12."""

    def test_current_payload(self):
        payload = make_phase_discovery_payload(METER_ID, BASE_TOPIC, "current", "current_l1")
        assert payload["name"] == "Current L1"
        assert payload["unique_id"] == f"kpm33b_{METER_ID}_current_l1"
        assert payload["state_topic"] == f"{BASE_TOPIC}/{METER_ID}/seconds"
        assert payload["device_class"] == "current"
        assert payload["state_class"] == "measurement"
        assert payload["unit_of_measurement"] == "A"
        assert payload["value_template"] == "{{ value_json.current_l1 }}"

    def test_power_payload(self):
        payload = make_phase_discovery_payload(METER_ID, BASE_TOPIC, "power", "active_power_l3")
        assert payload["name"] == "Active Power L3"
        assert payload["unique_id"] == f"kpm33b_{METER_ID}_active_power_l3"
        assert payload["device_class"] == "power"
        assert payload["unit_of_measurement"] == "kW"
        assert payload["value_template"] == "{{ value_json.active_power_l3 }}"

    def test_voltage_payload_uses_context_topic(self):
        payload = make_phase_discovery_payload(METER_ID, BASE_TOPIC, "voltage", "voltage_l2", context="Carport")
        assert payload["state_topic"] == f"{BASE_TOPIC}/Carport/{METER_ID}/seconds"
        assert payload["device_class"] == "voltage"
        assert payload["unit_of_measurement"] == "V"
        assert payload["device"]["name"] == "Carport"

    def test_total_power_factor_has_no_phase_suffix_and_no_unit(self):
        payload = make_phase_discovery_payload(METER_ID, BASE_TOPIC, "power_factor", "power_factor")
        assert payload["name"] == "Power Factor"
        assert "unit_of_measurement" not in payload

    def test_expire_after_follows_upload_frequency(self):
        payload = make_phase_discovery_payload(METER_ID, BASE_TOPIC, "current", "current_l1", upload_frequency=60)
        assert payload["expire_after"] == 150

    def test_unique_ids_do_not_collide_with_existing_sensors(self):
        existing = {
            make_power_discovery_payload(METER_ID, BASE_TOPIC)["unique_id"],
            make_energy_discovery_payload(METER_ID, BASE_TOPIC)["unique_id"],
        }
        phase_ids = {
            make_phase_discovery_payload(METER_ID, BASE_TOPIC, group, field)["unique_id"]
            for group, field in all_per_phase_fields()
        }
        assert not existing & phase_ids
        assert len(phase_ids) == len(all_per_phase_fields())

    def test_json_serializable(self):
        for group, field in all_per_phase_fields():
            json.dumps(make_phase_discovery_payload(METER_ID, BASE_TOPIC, group, field))


class TestPublishPerPhaseDiscovery:
    def test_enabled_groups_are_published(self):
        client = MagicMock()
        client.publish.return_value.rc = 0
        publish_discovery(client, METER_ID, BASE_TOPIC, per_phase_groups=["current"])
        published = {call.args[0]: call.args[1] for call in client.publish.call_args_list}
        for phase in ("l1", "l2", "l3"):
            topic = discovery_topic(METER_ID, f"current_{phase}")
            assert topic in published
            assert json.loads(published[topic])["device_class"] == "current"

    def test_disabled_groups_are_cleared(self):
        client = MagicMock()
        client.publish.return_value.rc = 0
        publish_discovery(client, METER_ID, BASE_TOPIC, per_phase_groups=["current"])
        published = {call.args[0]: call.args[1] for call in client.publish.call_args_list}
        assert published[discovery_topic(METER_ID, "voltage_l1")] == ""
        assert published[discovery_topic(METER_ID, "power_factor")] == ""

    def test_no_groups_clears_all_per_phase_configs(self):
        client = MagicMock()
        client.publish.return_value.rc = 0
        publish_discovery(client, METER_ID, BASE_TOPIC)
        published = {call.args[0]: call.args[1] for call in client.publish.call_args_list}
        for _, field in all_per_phase_fields():
            assert published[discovery_topic(METER_ID, field)] == ""

    def test_power_and_energy_still_published(self):
        client = MagicMock()
        client.publish.return_value.rc = 0
        publish_discovery(client, METER_ID, BASE_TOPIC, per_phase_groups=["current", "power"])
        published = {call.args[0]: call.args[1] for call in client.publish.call_args_list}
        assert json.loads(published[discovery_topic(METER_ID, "power")])["unique_id"] == f"kpm33b_{METER_ID}_power"
        assert json.loads(published[discovery_topic(METER_ID, "energy")])["unique_id"] == f"kpm33b_{METER_ID}_energy"


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
