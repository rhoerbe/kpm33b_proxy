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
- `homeassistant/sensor/kpm33b_33B1225950027/current_l1/config` (per-phase, opt-in)

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

### Per-Phase Sensors (opt-in)

Meters listed in `per_phase_device_ids` publish additional fields on the same
`<meter>/seconds` topic and get one extra entity per field. The `active_power` and
`active_energy` sensors, their `unique_id`s and their units are unaffected.

| Group | Output fields | Device class | Unit | Raw tags |
|-------|---------------|--------------|------|----------|
| `current` | `current_l1/l2/l3` | `current` | A | `ia`, `ib`, `ic` |
| `power` | `active_power_l1/l2/l3` | `power` | kW | `pa`, `pb`, `pc` |
| `voltage` | `voltage_l1/l2/l3` | `voltage` | V | `ua`, `ub`, `uc` |
| `power_factor` | `power_factor_l1/l2/l3`, `power_factor` | `power_factor` | — | `pfa`, `pfb`, `pfc`, `zglys` |

Entity names are `Current L1`, `Active Power L2`, … and unique IDs are
`kpm33b_<meter_id>_<field>` (e.g. `kpm33b_33B1225950027_current_l1`).

Groups that are not enabled for a meter get an empty retained discovery payload, so
removing a group from `per_phase_groups` removes the entities from Home Assistant.

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
| `expire_after` | Seconds until entity shows unavailable (upload interval × `expire_after_factor`) |
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
  upload_frequency_seconds: 60
  upload_frequency_minutes: 1
  upload_frequency_seconds_by_device:
    "33B1225950027": 30
  expire_after_factor: 2.5
  per_phase_device_ids:
    - "33B1225950027"
  per_phase_groups:
    - current
    - power
    - voltage
  device_contexts:
    "33B1225950029": "Heatpump Power"
    "33B1225950027": "Main Panel"
```

`upload_frequency_seconds_by_device` overrides the second-level interval for individual
meters — both the value sent to the meter by the config sender and the `expire_after`
of that meter's entities.

This produces:
- Topics: `kpm33b/Heatpump Power/33B1225950029/seconds`
- HA Device Name: "Heatpump Power"

## Availability Monitoring

The `expire_after` attribute enables Home Assistant's availability feature:
- Power and per-phase sensors: `upload interval (s) × expire_after_factor` (75 s for a 30 s interval)
- Energy sensors: `upload_frequency_minutes × 60 × expire_after_factor` (150 s for a 1 min interval)

If no data is received within this period, the entity shows as "unavailable".

The factor defaults to **2.5** and must be greater than 1. A factor at or near 1 makes
the entity expire between two publishes: with the former 1.5 and a meter publishing every
60 s while configured for 30 s, HA flagged the entity `unavailable` for ~15 s of every
minute (issue #12). 2.5 tolerates two missed publishes and still marks a dead meter
unavailable within ~75 s.

`expire_after` is deliberately kept (rather than dropped): without it, a meter that stops
publishing keeps its last value — a dead meter would read as a flat 0 kW forever.

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
  "expire_after": 75,
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
  "expire_after": 150,
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
