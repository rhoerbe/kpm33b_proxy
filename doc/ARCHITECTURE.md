# KPM33B Proxy Architecture

This document outlines the approved architecture for the KPM33B MQTT Proxy and its related components.

## Architectural Goal

The primary goal is to create a system that acts as a wrapper around the KPM33B energy meter devices (also called "meters"). 
Firstly, this isolates their raw, verbose message formats from the central MQTT broker, 
ensuring that only "clean and simple" messages are seen by downstream consumers. 
Secondly, the receiving system does not need to cope with device configuration or complex message formats.

## Design
### Components
- KPM33B energy meter devices a.k.a. meters
- Internal Broker (MQTT broker dedicated for the meters), implemented with mosquitto
- kpm33b_proxy (Subscribing to the internal broker, it transforms incoming messages and publishes it to the external broker)
- External broker (provides topics to the final consumer, such as Home Assistant)

This is achieved through a custom MQTT bridge architecture.
There are two message flows, (1) the *Data and Discovery Flow* and (2) the *Configuration Flow*.
All messages from and to the meters pass through an internal MQTT broker dedicated to the meters. 
The rationale to use a separate broker is that these messages should not be exposed to the central broker (implementing the Encapsulation Principle).
Communication is separated into two modules, each module implementing one flow:
1. *Data and Discovery Flow*: meter publishes to internal broker | kpm33b_proxy subscribes to broker,  
   transforms messages and publishes them to the central broker.
2. *Configuration Flow*: 
   2.1 config_sender subscribes to the central broker to discover meters | 
       config_sender publishes config data to internal broker | meter reads config updates
   2.2 meter publishes ack to internal broker | config_sender subscribes to ack and verifies ack message.
       If an ack message is not received withing 3 seconds, a message with severity=alert shall be logged.
   The config_sender module monitors for changes to config.yaml and updates meters when it detects an updated modification date. 
   The main idea is, that a discovery message triggers a config update. 

### Project Deliverables

1.  The `kpm33b_proxy.py` Application:
    *   Python application responsible for the *Data and Discovery Flow*.
    *   Concurrency: Using the standard paho-mqtt library with its default threading mode we can disregard concurrency issues.
    *   Run mode: Run as service controlled by systemctl
2.  The `config_sender.py` Application:
    *   A standalone Python application responsible for handling all device configuration.
    *   Concurrency: no need to consider 
    *   Run mode: Run as service controlled by systemctl
3.  The Internal Broker: Configuration and scripts to run a dedicated Mosquitto instance as a service controlled by systemctl. 
    This broker is the designated endpoint for all KPM33B devices and shall listen on 11883 by default.

### External Components

*   The Central Broker: A pre-existing, external MQTT broker that serves as the main message bus for the wider system.
    The IPv4 and port shall be configured in config.yaml

## Approved Architecture: Multi-Process Two-Broker Bridge

The architecture uses two separate applications (`kpm33b_proxy.py` and `config_sender.py`), running in their own processes, 
and two separate MQTT brokers.

### MQTT topic structure
The topic names are defined in config.yaml.

### Data Flow (kpm33b_proxy.py)

```
+-------------+      (1) Publish Raw Data                    +----------------+
| KPM33B      | -------------------------------------------> | Internal Broker| 
| Device(s)   | (meter_seconds_data, meter_minutes_data)     | (Mosquitto)    | 
+-------------+                                              +----------------+ 
                                                                     ^        
                                                                     | (2) Subscribe to meter_seconds_data, meter_minutes_data
                                                                     |
                                                             +-----------------+
                                                             | KPM33B Proxy    |   (3) Transform Data
                                                             |                 |
                                                             +-----------------+
                                                                     |
                                                                     | (4) Publish Simplified + Discovery Data
                                                                     v
                                                             +-----------------+
                                                             | Central Broker  |
                                                             | (Mosquitto)     |
+------------------+                                         +-----------------+
| Downstream App   |   (5) Subscribe profiled data                   |
| (e.g., Home Asst)| <-----------------------------------------------+
+------------------+
```
1.  Device to Internal Broker: Devices publish raw data to the Internal Broker using the meter_seconds_data, meter_minutes_data topics.
2.  Proxy subscribes: The `kpm33b_proxy.py` subscribes to the Internal Broker using the meter_seconds_data, meter_minutes_data topics.
3.  Proxy transforms: The proxy transforms as specified in doc/data_mapping.md.
4.  Proxy publishes: The proxy publishes the simplified version to the Central Broker. Topics are rewritten to /external_main_topic/deviceid/seconds and /external_main_topic/deviceid/minutes.
4.  Downstream Apps Subscribe: Consumers connect only to the Central Broker to receive the simplified data.

### Configuration Flow (config_sender.py)
```
        +--------------------+ (1) Subscribes to external main topic  +----------------+ 
        | Config Sender      | -------------------------------------> | Central Broker | 
        |                    |   (configurable in config.yaml)        |                |
        +--------------------+                                        +----------------+
             ^          |
             |          | (2) Publishes upload frequency to o MQTT_COMMOD_SET
             |          v
        +--------------------+    (3) Subscribes to MQTT_COMMOD_SET   +-----------------+
        | Internal Broker    | <------------------------------------- | KPM33B          |
        |                    |      (Subscribed to own topic)         | Device(s)       |
        +--------------------+                                        +-----------------+
                ^                                                         |
                |     (4) Publish Ack to MQTT_COMMOD_SET_REP               | 
                +---------------------------------------------------------+
```
1.  Config Sender subscribes: The `config_sender.py` application connects to the Central Broker and subscribes to the main topic. The subtopics are the meter device ids.
2.  Config Sender waits for discovery: When a new device is discovered by the proxy, the `config_sender.py` passes the new device ID to the next step. 
    A changed modification date of config.yaml is treated as a discovery of all existing devices. 
3.  Config Sender publishes Config: The `config_sender.py` connects to the internal broker and sends the upload frequency messages to the MQTT_COMMOD_SET_* topics.
4.  Device Receives Configuration: The meter subscribe to MQTT_COMMOD_SET_* and receive the configuration message from the KPM33B Broker.
5.  Device sends acknowledge to MQTT_COMMOD_SET_REP.
6.  Config Sender waits for acknowledge resulting in either an OK log entry or an ALERT log entry if there is a timeout.

## Deployment
Using systemd.