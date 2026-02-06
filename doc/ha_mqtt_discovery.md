# Home Assistant MQTT Discovery

This document describes the Home Assistant MQTT autodiscovery implementation for KPM33B power meters.

## Overview

The kpm33b_proxy automatically registers power meters with Home Assistant using the MQTT Discovery protocol. When a new meter is detected, discovery messages are published to the Home Assistant discovery topic prefix, causing HA to automatically create sensor entities without manual YAML configuration.

## Discovery Topics

Discovery config messages are published to:
```
homeassistant/sensor/kpm33b_<meter_id>/<sensor_type>/config
```

Examples:
- `homeassistant/sensor/kpm33b_33B1225950029/power/config`
- `homeassistant/sensor/kpm33b_33B1225950029/energy/config`

## Sensors Published

### Power Sensor
- **Metric**: Active power consumption
- **Unit**: kW
- **Device class**: `power`
- **State class**: `measurement`
- **State topic**: `kpm33b/<device_id>/seconds` (or `kpm33b/<context>/<device_id>/seconds`)
- **Value template**: `{{ value_json.active_power }}`

### Energy Sensor
- **Metric**: Cumulative energy consumption
- **Unit**: kWh
- **Device class**: `energy`
- **State class**: `total_increasing`
- **State topic**: `kpm33b/<device_id>/minutes` (or `kpm33b/<context>/<device_id>/minutes`)
- **Value template**: `{{ value_json.active_energy }}`

## Discovery Payload Attributes

| Attribute | Description |
|-----------|-------------|
| `name` | Sensor display name (e.g., "Active Power") |
| `unique_id` | Unique identifier enabling UI management (e.g., `kpm33b_33B1225950029_power`) |
| `state_topic` | Topic where sensor values are published |
| `device_class` | HA device class for icons and history (`power` or `energy`) |
| `state_class` | How HA handles state (`measurement` or `total_increasing`) |
| `unit_of_measurement` | Display unit (`kW` or `kWh`) |
| `value_template` | Jinja2 template to extract value from JSON payload |
| `suggested_display_precision` | Decimal places in UI (set to 0) |
| `expire_after` | Seconds until entity shows unavailable (upload_frequency × 1.5) |
| `device` | Device grouping object (see below) |

## Device Grouping

All sensors from the same physical meter are grouped under a single device in Home Assistant:

```json
{
  "device": {
    "identifiers": ["kpm33b_33B1225950029"],
    "name": "Heatpump Power",
    "manufacturer": "compere-power.com",
    "model": "KPM33B"
  }
}
```

The device name comes from `device_contexts` in config.yaml. If no context is configured, defaults to "KPM33B {meter_id}".

## Configuration

In `config.yaml`, the `device_contexts` field serves dual purpose:
1. **Topic hierarchy**: Adds context path to MQTT topics
2. **Device name**: Sets the friendly name in Home Assistant

```yaml
kpm33b_meters:
  upload_frequency_seconds: 30
  upload_frequency_minutes: 1
  device_contexts:
    "33B1225950029": "Heatpump Power"
    "33B1225950027": "Main Panel"
```

This produces:
- Topics: `kpm33b/Heatpump Power/33B1225950029/seconds`
- HA Device Name: "Heatpump Power"

## Availability Monitoring

The `expire_after` attribute enables Home Assistant's availability feature:
- Power sensors: `upload_frequency_seconds × 1.5` (e.g., 45 seconds for 30s interval)
- Energy sensors: `upload_frequency_minutes × 60 × 1.5` (e.g., 90 seconds for 1min interval)

If no data is received within this period, the entity shows as "unavailable".

## Discovery Timing

Discovery messages are published:
- On first message received from a new meter
- With `retain=True` so Home Assistant picks up the config on restart
- With `QoS=1` for reliable delivery

## Example Payloads

### Power Sensor Discovery
```json
{
  "name": "Active Power",
  "unique_id": "kpm33b_33B1225950029_power",
  "state_topic": "kpm33b/Heatpump Power/33B1225950029/seconds",
  "device_class": "power",
  "state_class": "measurement",
  "unit_of_measurement": "kW",
  "value_template": "{{ value_json.active_power }}",
  "suggested_display_precision": 0,
  "expire_after": 45,
  "device": {
    "identifiers": ["kpm33b_33B1225950029"],
    "name": "Heatpump Power",
    "manufacturer": "compere-power.com",
    "model": "KPM33B"
  }
}
```

### Energy Sensor Discovery
```json
{
  "name": "Active Energy",
  "unique_id": "kpm33b_33B1225950029_energy",
  "state_topic": "kpm33b/Heatpump Power/33B1225950029/minutes",
  "device_class": "energy",
  "state_class": "total_increasing",
  "unit_of_measurement": "kWh",
  "value_template": "{{ value_json.active_energy }}",
  "suggested_display_precision": 0,
  "expire_after": 90,
  "device": {
    "identifiers": ["kpm33b_33B1225950029"],
    "name": "Heatpump Power",
    "manufacturer": "compere-power.com",
    "model": "KPM33B"
  }
}
```

## Verification in Home Assistant

After the proxy starts and receives meter data:
1. Navigate to **Settings > Devices & Services > MQTT**
2. The device should appear automatically
3. Both power and energy sensors should be grouped under the device
4. Entities are editable via the cogwheel icon (enabled by `unique_id`)
5. History graphs show correct units without manual configuration
