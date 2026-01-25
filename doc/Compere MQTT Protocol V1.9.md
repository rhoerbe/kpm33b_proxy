# COMPERE MQTT Protocol Technical Reference (V1.9)

## 1. Purpose & Scope
The MQTT communication protocol is used to agree on the upload format and analysis method of power data. 

It mainly involves the timing of data upload and the Json message format transmitted by the MQTT protocol.
### Overview
This protocol is for power meter from COMPERE connecting server or cloud platform using MQTT communication protocol.

The connection is configured and connected according to the manual, where the supported meters are KPM37, KPM312, KPM31, KPM33B.

The connection to the server and the format of data transmission are the same for each meter, but the data tags are different.

### 2. Device Identification
The `id` field in all JSON payloads is a **13-bit meter code**. The IDs fin this project are: 
`33B1225950027`
`33B1225950028`
`33B1225950029`

## 3. The data to be uploaded and the time of uploading
The KPM33B supports data to be uploaded including real-time (second/minute level) electrical parameter data, daily and monthly data.
Real-time data second level electrical parameters include:
- 3 Phase line voltage and phase voltage 
- 3 Phase current 
- 3 phase and total active power
- 3 phase and total reactive power 
- 3 phase and total apparent power 
- 3 phase and total power factor
- frequency.
This is more than needed for an EMS (energy management system), and reduced to total active power and energy.


The Compere documentation explains data splitting, but the KPM33B does not split. 
As a safeguard, each data block must be checked to contain "isend":"1". 
If not, a "not implemented" exception must be communicated.

## 4. MQTT Topic Structure
The meters publish data to the proxy using following primary topics:
* MQTT_RT_DATA: Real-time electrical parameters (Second-level)
* MQTT_ENY_NOW: Energy consumption data (Minute-level)
* MQTT_TELEIND: Remote signal data (DI/DO status)
* MQTT_DAY_DATA: Energy consumption data (Day-level) 
* MQTT_TELECTRL_REP: Remote control response
* MQTT_SETTIME_(meterid last 8 bits): Single meter time synchronization
All devices use the same topic, the meter ID is contained in the data


## 5. Data Formatting & Transmission Logic
* **Payload Format:** All payloads are encoded in JSON.
* Data is never split into multiple packets for the KPMG33B. Therefore, the `"isend"` field is always "1".

## 6. Data Structure

See "COMPERE MQTT Protocol V1.9.pdf" and sample messages in tests/test_msg/*.json for details.

| Input Topic        | Tag     | Parameter Description      | Unit | Output Topic |
|:-------------------|:--------|:---------------------------|:-----|:-------------|
| `MQTT_RT_DATA` [4] | `zyggl` | Total Active Power (P)     | kW   | 
| `MQTT_ENY_NOW` [5] | `zygsz` | Import Total Active Energy | kWh  |


## 7. Sending Configuration Dta to Devices
The KPM33B subscribes to configuration topics at the MQTT broker. Following topics are relevant:
- Topic: MQTT_COMMOD_SET_<meterid last 8 bits>


  Payload: 
    {
      "oprid": "Operation id" // Nonce to match the response message; Format 32 bit strings
      "Cmd":   "0000", //Command CMD 0000 is second-level data setting. 0001 is minute-level data setting
      "value": "30",   //interval: Second level (in seconds): 30, 60, 300, 600, 900, 1200, 1800, 3600
                       //          Minute level (in minutes): 1, 5, 10, 15, 20, 30, 60
      "types": "1"     //1=Integer, 2=Float

  


## 8. Implementation Notes
* **Data Types:** Most values are transmitted as **floats** [5, 6].
* **Ignored Data:** To optimize Home Assistant storage, ignore voltage (`u`), current (`i`), frequency (`f`), apparent power (`s`), unbalance rates (`unb`/`inb`), and temperature tags (`ta`/`tb`/`tc`/`tn`) [6, 8, 15, 17].
Insight for Integration
When setting up the Python script, ensure it accounts for the fact that different meter models might send different quantities of packets. For example, the KPM37 splits minute-level data into 11 packets, while the KPM31A/B/C models typically upload all data in one package. The logic should always rely on the "isend": "1" flag rather than a fixed count of messages to ensure reliability across your three different devices.
Analogy: Think of the meter as a delivery service that sometimes has to split a large furniture order into several smaller boxes. The isend: 1 tag is the "final box" sticker; you shouldn't try to assemble the furniture until you see that sticker on the package.
* 