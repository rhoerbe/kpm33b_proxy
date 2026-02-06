"""Home Assistant MQTT autodiscovery for KPM33B meters.

Generates discovery payloads for power and energy sensors following
the HA MQTT discovery protocol.

Discovery topics:
  homeassistant/sensor/kpm33b_<meter_id>/power/config
  homeassistant/sensor/kpm33b_<meter_id>/energy/config

State topics (existing):
  kpm33b/<meter_id>/seconds  -> active_power (kW)
  kpm33b/<meter_id>/minutes  -> active_energy (kWh)
"""

import json
import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
MANUFACTURER = "compere-power.com"
MODEL = "KPM33B"


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


def make_power_discovery_payload(
    meter_id: str,
    base_topic: str,
    context: str | None = None,
    upload_frequency: int = 30,
) -> dict:
    """Generate HA discovery payload for the power sensor.

    Args:
        meter_id: The 13-character meter ID (e.g., "33B1225950027")
        base_topic: The base topic for meter data (e.g., "kpm33b")
        context: Optional context for topic hierarchy and device friendly name
        upload_frequency: Upload interval in seconds (for expire_after calculation)

    Returns:
        Discovery payload dict ready for JSON serialization
    """
    if context:
        state_topic = f"{base_topic}/{context}/{meter_id}/seconds"
    else:
        state_topic = f"{base_topic}/{meter_id}/seconds"
    return {
        "name": "Active Power",
        "unique_id": f"kpm33b_{meter_id}_power",
        "state_topic": state_topic,
        "device_class": "power",
        "state_class": "measurement",
        "unit_of_measurement": "kW",
        "value_template": "{{ value_json.active_power }}",
        "suggested_display_precision": 0,
        "expire_after": int(upload_frequency * 1.5),
        "device": _device_block(meter_id, context),
    }


def make_energy_discovery_payload(
    meter_id: str,
    base_topic: str,
    context: str | None = None,
    upload_frequency: int = 1,
) -> dict:
    """Generate HA discovery payload for the energy sensor.

    Args:
        meter_id: The 13-character meter ID (e.g., "33B1225950027")
        base_topic: The base topic for meter data (e.g., "kpm33b")
        context: Optional context for topic hierarchy and device friendly name
        upload_frequency: Upload interval in minutes (for expire_after calculation)

    Returns:
        Discovery payload dict ready for JSON serialization
    """
    if context:
        state_topic = f"{base_topic}/{context}/{meter_id}/minutes"
    else:
        state_topic = f"{base_topic}/{meter_id}/minutes"
    return {
        "name": "Active Energy",
        "unique_id": f"kpm33b_{meter_id}_energy",
        "state_topic": state_topic,
        "device_class": "energy",
        "state_class": "total_increasing",
        "unit_of_measurement": "kWh",
        "value_template": "{{ value_json.active_energy }}",
        "suggested_display_precision": 0,
        "expire_after": int(upload_frequency * 60 * 1.5),
        "device": _device_block(meter_id, context),
    }


def discovery_topic(meter_id: str, sensor_type: str) -> str:
    """Generate the HA discovery config topic.

    Args:
        meter_id: The 13-character meter ID
        sensor_type: Either "power" or "energy"

    Returns:
        Discovery topic string (e.g., "homeassistant/sensor/kpm33b_33B1225950027/power/config")
    """
    return f"{DISCOVERY_PREFIX}/sensor/kpm33b_{meter_id}/{sensor_type}/config"


def publish_discovery(
    client: mqtt.Client,
    meter_id: str,
    base_topic: str,
    context: str | None = None,
    upload_freq_seconds: int = 30,
    upload_freq_minutes: int = 1,
) -> None:
    """Publish HA autodiscovery messages for a meter.

    Publishes discovery configs for both power and energy sensors.
    Uses QoS 1 and retain=True so HA picks up the config on restart.

    Args:
        client: Connected MQTT client (to the central broker)
        meter_id: The 13-character meter ID
        base_topic: The base topic for meter data (e.g., "kpm33b")
        context: Optional context for topic hierarchy and device friendly name
        upload_freq_seconds: Upload interval for power data (seconds)
        upload_freq_minutes: Upload interval for energy data (minutes)
    """
    # Power sensor discovery
    power_topic = discovery_topic(meter_id, "power")
    power_payload = json.dumps(make_power_discovery_payload(meter_id, base_topic, context, upload_freq_seconds))
    result = client.publish(power_topic, power_payload, qos=1, retain=True)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info("Published HA discovery for %s power sensor", meter_id)
    else:
        logger.error("Failed to publish HA discovery for %s power: rc=%d", meter_id, result.rc)

    # Energy sensor discovery
    energy_topic = discovery_topic(meter_id, "energy")
    energy_payload = json.dumps(make_energy_discovery_payload(meter_id, base_topic, context, upload_freq_minutes))
    result = client.publish(energy_topic, energy_payload, qos=1, retain=True)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info("Published HA discovery for %s energy sensor", meter_id)
    else:
        logger.error("Failed to publish HA discovery for %s energy: rc=%d", meter_id, result.rc)
