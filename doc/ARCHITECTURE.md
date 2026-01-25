# KPM33B Proxy Architecture

This document outlines the approved architecture for the KPM33B MQTT Proxy and its related components.

## Architectural Goal

The primary goal is to create a system that acts as a wrapper around the KPM33B energy meter devices (also called "meters"). 
Firstly, this isolates their raw, verbose message formats from the central MQTT broker, 
ensuring that only "clean and simple" messages are seen by downstream consumers. 
Secondly, the receiving system does not need to copy with device configuration or complex message formats.

## Design
### Components
- KPM33B energy meter devices a.k.a. meters
- Internal Broker (MQTT broker dedicated for the meters), implemented with mosquitto
- kpm33b_proxy (Subscribing to the internal broker, it transforms incoming messages and publishes it to the external broker)
- External broker (provides topics to the consumer, such as Home Assistant)

This is achieved through a custom MQTT bridge architecture.
There are two message flows, (1) the *Data and Discovery Flow* and (2) the *Configuration Flow*.
All messages from and to the meters pass through an internal MQTT broker dedicated to the meters. 
The rationale is that these messages should not be exposed to the central broker (implementing the Encapsulation Principle).
Communication is separated into two modules, each module implementing one flow:
1. *Data and Discovery Flow*: meter publishes to internal broker | kpm33b_proxy subscribes to broker,  
   transforms messages and publishes them to the central broker (data) and back to the internal broker (meter discovery)
2. *Configuration Flow*: 
   2.1 config_sender publishes config data to internal broker | meter reads config updates
   2.2 meter publishes ack to internal broker | config_sender subscribes to ack and verifies ack message
   The config_sender module subscribes to meter discovery messages. 
   The main idea is, that a discovery message triggers a config update. 
   To reduce message noise, config messages are sent only when the config has not been sent on the same day, 
   or config.yaml has been changed since the last config update. 

## System Components & Concurrency Model

The burden of concurrency is only with the MQTT broker. 
Both kpm33b_proxy and config_sender subscribe to topics that can be viewed sequentially. 

### Project Deliverables

1.  **The `kpm33b_proxy.py` Application (Multi-Threaded):**
    *   **Role:** A dedicated MQTT bridge responsible for the *Data and Discovery Flow*.
    *   **Concurrency:** This application is **multi-threaded**. It uses threading to manage several concurrent tasks:
        1.  Maintaining a persistent connection to the `KPM33B Broker` to receive device data (Main Thread).
        2.  Maintaining a persistent connection to the `Central Broker` to publish simplified data (Background Thread).
        3.  Periodically publishing status updates to the `Central Broker` (Background Thread).

2.  **The `config_sender.py` Application (Multi-Threaded):**
    *   **Role:** A separate, standalone application responsible for handling all device configuration.
    *   **Concurrency:** This application is also **multi-threaded** to manage its concurrent tasks 
        (connecting to two brokers, running a periodic sender loop).

3.  **The KPM33B Broker:** Configuration and scripts to run a dedicated Mosquitto instance. This broker is the designated endpoint for all KPM33B devices.

### External Components

*   **The Central Broker:** A pre-existing, external MQTT broker that serves as the main message bus for the wider system.

## Approved Architecture: Multi-Process Two-Broker Bridge

The architecture uses two separate applications (`kpm33b_proxy.py` and `config_sender.py`), running in their own **processes**, 
and two separate MQTT brokers.

### Data & Discovery Flow

```
+-------------+      (1) Publish Raw Data        +--------------+
| KPM33B      | -------------------------------> | KPM33B Broker| <-----------+
| Device(s)   |      (MQTT_RT_DATA, etc.)        | (Mosquitto 1)|             |
+-------------+                                  +--------------+             |
                                                         ^                    |
                                                         | (2) Subscribe      |
                                                         |                    |
                                                 +-----------------+          |
                                                 | kpm33b_proxy.py | ---------+
                                                 | (This App)      | (6) Publish discovered devices
                                                 +-----------------+
                                                         |
                                                         | (3) Transform Data
                                                         |
                                                         | (4) Publish Simplified Data
                                                         v
                                                 +-----------------+
                                                 | Central Broker  |
                                                 | (Mosquitto 2)   |
+------------------+                             +-----------------+
| Downstream App   |   (5) Subscribe profiled data       |
| (e.g., Home Asst)| <-----------------------------------+
+------------------+
```
1.  **Device to KPM33B Broker:** Devices publish raw data to the **KPM33B Broker**.
2.  **Proxy Subscribes:** The `kpm33b_proxy.py` connects to the **KPM33B Broker** and subscribes to data topics.
3.  **Proxy Transforms and Publishes:** The proxy transforms the raw data and publishes the simplified version to the **Central Broker**.
4.  **Proxy Publishes Discovery:** Upon seeing a device for the first time, `kpm33b_proxy.py` also publishes a discovery message to a specific topic (`kpm33b/discovery/<device_id>`) on the **Central Broker**.
5.  **Downstream Apps Subscribe:** Consumers connect only to the **Central Broker** to receive the simplified data.

### Configuration Flow
```
+--------------------+      (1) Subscribes to       +----------------+ (2) Receives Discovery &   +-------------------+
| config_sender.py   | <--------------------------- | Central Broker | <------------------------- | kpm33b_proxy.py   |
| (Config App)       |   (kpm33b/discovery/+)       | (External)     |                            | (Data Bridge)     |
+--------------------+                              +----------------+                            +-------------------+
        |
        | (3) Publishes Config
        |
+----------------+      (4) Receives Config         +-------------+
| KPM33B Broker  | <------------------------------- | KPM33B      |
| (Deliverable)  |      (Subscribed to own topic)   | Device(s)   |
+----------------+                                  +-------------+
```
1.  **Config Sender Subscribes:** The `config_sender.py` application connects to the **Central Broker** and subscribes to the discovery topic (`kpm33b/discovery/+`).
2.  **Config Sender Receives Discovery:** When a new device is discovered by the proxy, the `config_sender.py` receives the discovery message and adds the new device ID to its list of known devices.
3.  **Config Sender Publishes Config:** The `config_sender.py` connects to the **KPM33B Broker** and periodically sends configuration messages to the topics for its known devices.
4.  **Device Receives Configuration:** The device receives the configuration message from the KPM33B Broker.

### Device Configuration Strategy (Hybrid Model)
*Explanation of hybrid model remains the same.*
