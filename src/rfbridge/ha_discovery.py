"""Home Assistant MQTT autodiscovery for 433 MHz RF bridge sensors.

Publishes discovery messages for temperature, humidity, and battery_low entities
per sensor defined in sensors.yaml.

Discovery topics:
  homeassistant/sensor/433rfbridge_<friendly_name>_temperature/config
  homeassistant/sensor/433rfbridge_<friendly_name>_humidity/config
  homeassistant/sensor/433rfbridge_<friendly_name>_battery_low/config

State topics:
  tele/433rfbridge/<friendly_name>/state
"""

import json
import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
MANUFACTURER = "generic"
MODEL = "Nexus-compatible 433 MHz sensor"


def _device_block(friendly_name: str) -> dict:
    return {
        "identifiers": [f"433rfbridge_{friendly_name}"],
        "name": friendly_name.replace("_", " ").title(),
        "manufacturer": MANUFACTURER,
        "model": MODEL,
    }


def _state_topic(output_topic_prefix: str, friendly_name: str) -> str:
    return f"{output_topic_prefix}/{friendly_name}/state"


def make_temperature_discovery_payload(friendly_name: str, output_topic_prefix: str) -> dict:
    return {
        "name": "Temperature",
        "unique_id": f"433rfbridge_{friendly_name}_temperature",
        "state_topic": _state_topic(output_topic_prefix, friendly_name),
        "device_class": "temperature",
        "state_class": "measurement",
        "unit_of_measurement": "°C",
        "value_template": "{{ value_json.temperature }}",
        "suggested_display_precision": 1,
        "device": _device_block(friendly_name),
    }


def make_humidity_discovery_payload(friendly_name: str, output_topic_prefix: str) -> dict:
    return {
        "name": "Humidity",
        "unique_id": f"433rfbridge_{friendly_name}_humidity",
        "state_topic": _state_topic(output_topic_prefix, friendly_name),
        "device_class": "humidity",
        "state_class": "measurement",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.humidity }}",
        "device": _device_block(friendly_name),
    }


def make_battery_low_discovery_payload(friendly_name: str, output_topic_prefix: str) -> dict:
    return {
        "name": "Battery Low",
        "unique_id": f"433rfbridge_{friendly_name}_battery_low",
        "state_topic": _state_topic(output_topic_prefix, friendly_name),
        "device_class": "battery",
        "entity_category": "diagnostic",
        "value_template": "{{ 'ON' if value_json.battery_low else 'OFF' }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device": _device_block(friendly_name),
    }


def discovery_topic(friendly_name: str, sensor_type: str) -> str:
    return f"{DISCOVERY_PREFIX}/sensor/433rfbridge_{friendly_name}_{sensor_type}/config"


def publish_discovery(
    client: mqtt.Client,
    friendly_name: str,
    output_topic_prefix: str,
) -> None:
    """Publish HA autodiscovery messages for one RF sensor (temperature, humidity, battery_low)."""
    entities = [
        ("temperature", discovery_topic(friendly_name, "temperature"), make_temperature_discovery_payload(friendly_name, output_topic_prefix)),
        ("humidity", discovery_topic(friendly_name, "humidity"), make_humidity_discovery_payload(friendly_name, output_topic_prefix)),
        ("battery_low", discovery_topic(friendly_name, "battery_low"), make_battery_low_discovery_payload(friendly_name, output_topic_prefix)),
    ]
    for entity_type, topic, payload in entities:
        result = client.publish(topic, json.dumps(payload), qos=1, retain=True)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Published HA discovery for %s/%s", friendly_name, entity_type)
        else:
            logger.error("Failed HA discovery publish for %s/%s: rc=%d", friendly_name, entity_type, result.rc)
