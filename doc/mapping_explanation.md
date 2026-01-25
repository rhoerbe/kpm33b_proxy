# Data Mapping Specification

This document specifies the mapping between the raw JSON data received from the KPM33B power meter 
and the simplified JSON data produced by the `transform_data` function in `kpm33b_proxy`.

The `Compere MQTT Protocol V1.9.md` document specifies the data format for various topics, 
including `MQTT_RT_DATA` (real-time data) and `MQTT_ENY_NOW` (energy data).

A key feature of the KPMG33B proxy is to reduce the complexity of the data structure by transforming the data using the following profile.
The profile defines how the meter MQTT messages are mapped as follows:

1. Separate topics per meter, with the meter id as subtopic.
2. All subtopics are underneath a user-configurable root topics (default "compere")
3. Selected tags from the message are mapped to the output message, using more human readable names, defined in this table: 

| Input Topic    | Tag     | Output Name    | Parameter Description      | Unit | 
|:---------------|:--------|:---------------|:---------------------------|:-----|
| `MQTT_RT_DATA` | `id`    | sub topic name | meter id                   |      | 
| `MQTT_RT_DATA` | `time`  | time           | YYYYMMDDHHMMDD             |      | 
| `MQTT_RT_DATA` | `zyggl` | active_power   | Total Active Power (P)     | kW   | 
| `MQTT_ENY_NOW` | `id`    | sub topic name | meter id                   |      | 
| `MQTT_ENY_NOW` | `time`  | time           | YYYYMMDDHHMMDD             |      | 
| `MQTT_ENY_NOW` | `zygsz` | active_energy  | Import Total Active Energy | kWh  |


### Test Data (`MQTT_RT_DATA.json`)

Unit tests must use the files in tests/test_msg to validate the transformation. 
It also includes messages where a tag is missing and the expected result is a null value in the corresponding output field.

### Raw Data Examples

`MQTT_RT_DATA`
```json
{"id":"33B1225950027","ia":9.735,"ib":9.658,"ic":9.655,"ua":229.097,"ub":231.567,"uc":232.529,"uab":398.949,"ubc":401.920,"uca":399.784,"pa":2.2229,"pb":2.2293,"pc":2.2382,"zyggl":6.6905,"qa":-0.1648,"qb":-0.1649,"qc":-0.1632,"zwggl":-0.4930,"sa":2.2304,"sb":2.2366,"sc":2.2452,"zszgl":6.7122,"pfa":0.996,"pfb":0.996,"pfc":0.996,"zglys":0.996,"f":49.959,"uxja":0.000,"uxjb":239.774,"uxjc":119.874,"ixja":355.691,"ixjb":235.434,"ixjc":115.615,"unb":1.485,"inb":0.823,"pdm":6.6898,"qdm":-0.4971,"sdm":6.7118,"iadm":9.6838,"ibdm":9.6380,"icdm":9.6717,"time":"20260112163900","isend":"1"}
```

`MQTT_ENY_NOW`
```json
{
    "id": "33B1225950027",
    "isend": "1",
    "zygsz": 163.486,
    "fygsz": 0.000,
    "zwgsz": 0.000,
    "fwgsz": 11.085,
    "zszsz": 164.331,
    "zyjsz": 8.668,
    "fyjsz": 0.000,
    "zyfsz": 25.344,
    "fyfsz": 0.000,
    "zypsz": 60.573,
    "fypsz": 0.000,
    "zyvsz": 68.898,
    "fyvsz": 0.000,
    "zydvsz": 0.000,
    "fydvsz": 0.000,
    "time":"20260117211500",
    "isend":"1"
}
```
