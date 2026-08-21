"""Home Assistant MQTT autodiscovery for KPM33B meters.

Generates discovery payloads for power, energy and (optionally) per-phase
sensors following the HA MQTT discovery protocol.

Discovery topics:
  homeassistant/sensor/kpm33b_<meter_id>/power/config
  homeassistant/sensor/kpm33b_<meter_id>/energy/config
  homeassistant/sensor/kpm33b_<meter_id>/<per_phase_field>/config

State topics (existing):
  kpm33b/<meter_id>/seconds  -> active_power (kW), optional per-phase fields
  kpm33b/<meter_id>/minutes  -> active_energy (kWh)
"""

import json
import logging
from collections.abc import Sequence

import paho.mqtt.client as mqtt

from src.transform import PER_PHASE_GROUPS

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
MANUFACTURER = "compere-power.com"
MODEL = "KPM33B"

# expire_after = publish interval × this factor. Must be > 1: with a factor of
# 1.5 and a meter publishing slightly late, HA flags the entity `unavailable`
# between every two messages (issue #12). 2.5 tolerates two missed publishes
# while still detecting a genuinely dead meter.
EXPIRE_AFTER_FACTOR = 2.5

# HA metadata per per-phase measurement group (see transform.PER_PHASE_GROUPS)
PER_PHASE_SENSOR_META: dict[str, dict] = {
    "current": {"label": "Current", "device_class": "current", "unit_of_measurement": "A", "precision": 2},
    "power": {"label": "Active Power", "device_class": "power", "unit_of_measurement": "kW", "precision": 3},
    "voltage": {"label": "Voltage", "device_class": "voltage", "unit_of_measurement": "V", "precision": 1},
    "power_factor": {
        "label": "Power Factor", "device_class": "power_factor", "unit_of_measurement": None, "precision": 3
    },
}


def _device_block(meter_id: str, friendly_name: str | None = None) -> dict:
    """Generate the shared device block for a meter.

    Args:
        meter_id: The 13-character meter ID
        friendly_name: Optional friendly name for the device (from device_contexts)
    """
    name = friendly_name if friendly_name else f"KPM33B {meter_id}"
    return {
        "identifiers": [f"kpm33b_{meter_id}"],
        "name": name,
        "manufacturer": MANUFACTURER,
        "model": MODEL,
    }


def _seconds_state_topic(meter_id: str, base_topic: str, context: str | None) -> str:
    if context:
        return f"{base_topic}/{context}/{meter_id}/seconds"
    return f"{base_topic}/{meter_id}/seconds"


def _minutes_state_topic(meter_id: str, base_topic: str, context: str | None) -> str:
    if context:
        return f"{base_topic}/{context}/{meter_id}/minutes"
    return f"{base_topic}/{meter_id}/minutes"


def _expire_after(interval_seconds: float, factor: float = EXPIRE_AFTER_FACTOR) -> int:
    return int(interval_seconds * factor)


def make_power_discovery_payload(
    meter_id: str,
    base_topic: str,
    context: str | None = None,
    upload_frequency: int = 30,
    expire_after_factor: float = EXPIRE_AFTER_FACTOR,
) -> dict:
    """Generate HA discovery payload for the power sensor.

    Args:
        meter_id: The 13-character meter ID (e.g., "33B1225950027")
        base_topic: The base topic for meter data (e.g., "kpm33b")
        context: Optional context for topic hierarchy and device friendly name
        upload_frequency: Upload interval in seconds (for expire_after calculation)
        expire_after_factor: Multiple of the upload interval before HA expires the entity

    Returns:
        Discovery payload dict ready for JSON serialization
    """
    return {
        "name": "Active Power",
        "unique_id": f"kpm33b_{meter_id}_power",
        "state_topic": _seconds_state_topic(meter_id, base_topic, context),
        "device_class": "power",
        "state_class": "measurement",
        "unit_of_measurement": "kW",
        "value_template": "{{ value_json.active_power }}",
        "suggested_display_precision": 0,
        "expire_after": _expire_after(upload_frequency, expire_after_factor),
        "device": _device_block(meter_id, context),
    }


def make_energy_discovery_payload(
    meter_id: str,
    base_topic: str,
    context: str | None = None,
    upload_frequency: int = 1,
    expire_after_factor: float = EXPIRE_AFTER_FACTOR,
) -> dict:
    """Generate HA discovery payload for the energy sensor.

    Args:
        meter_id: The 13-character meter ID (e.g., "33B1225950027")
        base_topic: The base topic for meter data (e.g., "kpm33b")
        context: Optional context for topic hierarchy and device friendly name
        upload_frequency: Upload interval in minutes (for expire_after calculation)
        expire_after_factor: Multiple of the upload interval before HA expires the entity

    Returns:
        Discovery payload dict ready for JSON serialization
    """
    return {
        "name": "Active Energy",
        "unique_id": f"kpm33b_{meter_id}_energy",
        "state_topic": _minutes_state_topic(meter_id, base_topic, context),
        "device_class": "energy",
        "state_class": "total_increasing",
        "unit_of_measurement": "kWh",
        "value_template": "{{ value_json.active_energy }}",
        "suggested_display_precision": 0,
        "expire_after": _expire_after(upload_frequency * 60, expire_after_factor),
        "device": _device_block(meter_id, context),
    }


def _sensor_name(group: str, field: str) -> str:
    """Human-readable entity name, e.g. ("current", "current_l1") -> "Current L1"."""
    label = PER_PHASE_SENSOR_META[group]["label"]
    phase = field.rsplit("_", 1)[-1]
    if phase in ("l1", "l2", "l3"):
        return f"{label} {phase.upper()}"
    return label


def make_phase_discovery_payload(
    meter_id: str,
    base_topic: str,
    group: str,
    field: str,
    context: str | None = None,
    upload_frequency: int = 30,
    expire_after_factor: float = EXPIRE_AFTER_FACTOR,
) -> dict:
    """Generate HA discovery payload for one per-phase sensor.

    Args:
        meter_id: The 13-character meter ID
        base_topic: The base topic for meter data (e.g., "kpm33b")
        group: Per-phase group name (see transform.PER_PHASE_GROUPS)
        field: Output field name within that group (e.g., "current_l1")
        context: Optional context for topic hierarchy and device friendly name
        upload_frequency: Upload interval in seconds (for expire_after calculation)
        expire_after_factor: Multiple of the upload interval before HA expires the entity

    Returns:
        Discovery payload dict ready for JSON serialization
    """
    meta = PER_PHASE_SENSOR_META[group]
    payload = {
        "name": _sensor_name(group, field),
        "unique_id": f"kpm33b_{meter_id}_{field}",
        "state_topic": _seconds_state_topic(meter_id, base_topic, context),
        "device_class": meta["device_class"],
        "state_class": "measurement",
        "value_template": f"{{{{ value_json.{field} }}}}",
        "suggested_display_precision": meta["precision"],
        "expire_after": _expire_after(upload_frequency, expire_after_factor),
        "device": _device_block(meter_id, context),
    }
    if meta["unit_of_measurement"] is not None:
        payload["unit_of_measurement"] = meta["unit_of_measurement"]
    return payload


def per_phase_fields(groups: Sequence[str]) -> list[tuple[str, str]]:
    """Return (group, field) pairs for the given per-phase groups, in config order."""
    return [(group, field) for group in groups for field in PER_PHASE_GROUPS[group].values()]


def all_per_phase_fields() -> list[tuple[str, str]]:
    """Return (group, field) pairs for every known per-phase group."""
    return per_phase_fields(list(PER_PHASE_GROUPS))


def discovery_topic(meter_id: str, sensor_type: str) -> str:
    """Generate the HA discovery config topic.

    Args:
        meter_id: The 13-character meter ID
        sensor_type: "power", "energy" or a per-phase field name (e.g. "current_l1")

    Returns:
        Discovery topic string (e.g., "homeassistant/sensor/kpm33b_33B1225950027/power/config")
    """
    return f"{DISCOVERY_PREFIX}/sensor/kpm33b_{meter_id}/{sensor_type}/config"


def _publish(client: mqtt.Client, topic: str, payload: str, meter_id: str, label: str) -> None:
    result = client.publish(topic, payload, qos=1, retain=True)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info("Published HA discovery for %s %s sensor", meter_id, label)
    else:
        logger.error("Failed to publish HA discovery for %s %s: rc=%d", meter_id, label, result.rc)


def publish_discovery(
    client: mqtt.Client,
    meter_id: str,
    base_topic: str,
    context: str | None = None,
    upload_freq_seconds: int = 30,
    upload_freq_minutes: int = 1,
    per_phase_groups: Sequence[str] = (),
    expire_after_factor: float = EXPIRE_AFTER_FACTOR,
) -> None:
    """Publish HA autodiscovery messages for a meter.

    Publishes discovery configs for the power and energy sensors, plus one
    sensor per per-phase field of the enabled groups. Per-phase configs of
    groups that are *not* enabled are cleared (empty retained payload) so that
    disabling a group in config.yaml removes the entities from HA.

    Uses QoS 1 and retain=True so HA picks up the config on restart.

    Args:
        client: Connected MQTT client (to the central broker)
        meter_id: The 13-character meter ID
        base_topic: The base topic for meter data (e.g., "kpm33b")
        context: Optional context for topic hierarchy and device friendly name
        upload_freq_seconds: Upload interval for power data (seconds)
        upload_freq_minutes: Upload interval for energy data (minutes)
        per_phase_groups: Per-phase groups to publish for this meter
        expire_after_factor: Multiple of the upload interval before HA expires an entity
    """
    power_payload = json.dumps(
        make_power_discovery_payload(meter_id, base_topic, context, upload_freq_seconds, expire_after_factor)
    )
    _publish(client, discovery_topic(meter_id, "power"), power_payload, meter_id, "power")

    energy_payload = json.dumps(
        make_energy_discovery_payload(meter_id, base_topic, context, upload_freq_minutes, expire_after_factor)
    )
    _publish(client, discovery_topic(meter_id, "energy"), energy_payload, meter_id, "energy")

    enabled = per_phase_fields(per_phase_groups)
    for group, field in enabled:
        payload = json.dumps(
            make_phase_discovery_payload(
                meter_id, base_topic, group, field, context, upload_freq_seconds, expire_after_factor
            )
        )
        _publish(client, discovery_topic(meter_id, field), payload, meter_id, field)

    enabled_fields = {field for _, field in enabled}
    for _, field in all_per_phase_fields():
        if field in enabled_fields:
            continue
        client.publish(discovery_topic(meter_id, field), "", qos=1, retain=True)
    logger.debug("Cleared disabled per-phase discovery configs for %s", meter_id)
