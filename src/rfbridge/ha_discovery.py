"""Home Assistant MQTT autodiscovery for 433 MHz RF bridge sensors.

Publishes discovery messages for temperature, humidity, and battery_low entities
per sensor defined in sensors.yaml.

Discovery topics:
  homeassistant/sensor/433rfbridge_<friendly_name>_temperature/config
  homeassistant/sensor/433rfbridge_<friendly_name>_humidity/config
  homeassistant/binary_sensor/433rfbridge_<friendly_name>_battery_low/config

unique_id is based on (protocol, channel) — the stable physical key — so renaming
a sensor in sensors.yaml updates the existing HA entity rather than creating a new one.

State topics:
  tele/433rfbridge/<friendly_name>/state
"""

import json
import logging

import paho.mqtt.client as mqtt

from src.rfbridge.utils import sanitise_topic_name

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
MANUFACTURER = "generic"
MODEL = "Nexus-compatible 433 MHz sensor"


def _stable_id(protocol: str, channel: int) -> str:
    """Stable identifier derived from physical sensor properties, survives renames."""
    return f"433rfbridge_{protocol}_ch{channel}"


def _device_block(friendly_name: str, protocol: str, channel: int) -> dict:
    return {
        "identifiers": [_stable_id(protocol, channel)],
        "name": friendly_name.replace("_", " ").title(),
        "manufacturer": MANUFACTURER,
        "model": MODEL,
    }


def _state_topic(output_topic_prefix: str, friendly_name: str) -> str:
    return f"{output_topic_prefix}/{sanitise_topic_name(friendly_name)}/state"


def make_temperature_discovery_payload(
    friendly_name: str, protocol: str, channel: int, output_topic_prefix: str
) -> dict:
    return {
        "name": "Temperature",
        "unique_id": f"{_stable_id(protocol, channel)}_temperature",
        "state_topic": _state_topic(output_topic_prefix, friendly_name),
        "device_class": "temperature",
        "state_class": "measurement",
        "unit_of_measurement": "°C",
        "value_template": "{{ value_json.temperature }}",
        "suggested_display_precision": 1,
        "device": _device_block(friendly_name, protocol, channel),
    }


def make_humidity_discovery_payload(
    friendly_name: str, protocol: str, channel: int, output_topic_prefix: str
) -> dict:
    return {
        "name": "Humidity",
        "unique_id": f"{_stable_id(protocol, channel)}_humidity",
        "state_topic": _state_topic(output_topic_prefix, friendly_name),
        "device_class": "humidity",
        "state_class": "measurement",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.humidity }}",
        "device": _device_block(friendly_name, protocol, channel),
    }


def make_battery_low_discovery_payload(
    friendly_name: str, protocol: str, channel: int, output_topic_prefix: str
) -> dict:
    """Binary sensor — device_class 'battery' expects ON=low, OFF=OK."""
    return {
        "name": "Battery Low",
        "unique_id": f"{_stable_id(protocol, channel)}_battery_low",
        "state_topic": _state_topic(output_topic_prefix, friendly_name),
        "device_class": "battery",
        "entity_category": "diagnostic",
        "value_template": "{{ 'ON' if value_json.battery_low else 'OFF' }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device": _device_block(friendly_name, protocol, channel),
    }


def discovery_topic(friendly_name: str, sensor_type: str) -> str:
    component = "binary_sensor" if sensor_type == "battery_low" else "sensor"
    safe = sanitise_topic_name(friendly_name)
    return f"{DISCOVERY_PREFIX}/{component}/433rfbridge_{safe}_{sensor_type}/config"


def clear_discovery(client: mqtt.Client, friendly_name: str) -> None:
    """Remove all retained discovery entries for a sensor (e.g. after rename/removal)."""
    safe = sanitise_topic_name(friendly_name)
    for sensor_type in ("temperature", "humidity"):
        topic = f"{DISCOVERY_PREFIX}/sensor/433rfbridge_{safe}_{sensor_type}/config"
        client.publish(topic, b"", qos=1, retain=True)
    topic = f"{DISCOVERY_PREFIX}/binary_sensor/433rfbridge_{safe}_battery_low/config"
    client.publish(topic, b"", qos=1, retain=True)
    logger.info("Cleared HA discovery entries for removed/renamed sensor '%s'", friendly_name)


def publish_discovery(
    client: mqtt.Client,
    friendly_name: str,
    protocol: str,
    channel: int,
    output_topic_prefix: str,
) -> None:
    """Publish HA autodiscovery messages for one RF sensor (temperature, humidity, battery_low).

    unique_id is keyed on (protocol, channel) so HA tracks the entity across renames.
    Any stale sensor-component entry for battery_low is cleared on each publish.
    """
    # Clear stale sensor-component entry for battery_low (published before binary_sensor fix)
    stale_topic = f"{DISCOVERY_PREFIX}/sensor/433rfbridge_{sanitise_topic_name(friendly_name)}_battery_low/config"
    client.publish(stale_topic, b"", qos=1, retain=True)

    entities = [
        ("temperature", discovery_topic(friendly_name, "temperature"),
         make_temperature_discovery_payload(friendly_name, protocol, channel, output_topic_prefix)),
        ("humidity", discovery_topic(friendly_name, "humidity"),
         make_humidity_discovery_payload(friendly_name, protocol, channel, output_topic_prefix)),
        ("battery_low", discovery_topic(friendly_name, "battery_low"),
         make_battery_low_discovery_payload(friendly_name, protocol, channel, output_topic_prefix)),
    ]
    for entity_type, topic, payload in entities:
        result = client.publish(topic, json.dumps(payload), qos=1, retain=True)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Published HA discovery for %s/%s", friendly_name, entity_type)
        else:
            logger.error("Failed HA discovery publish for %s/%s: rc=%d", friendly_name, entity_type, result.rc)
