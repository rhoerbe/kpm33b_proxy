#!/bin/bash

# Template to subscribe to original KPM33B messages
export MQTT_USERID=mqtt
export MQTT_PASSWORD=<secret>

# all messages with topic
mosquitto_sub -L mqtt://$MQTT_USERID:$MQTT_PASSWORD@localhost:11883/# -v

# all energy messages of a specific meter
mosquitto_sub -L mqtt://localhost:11883/MQTT_ENY_NOW | \
    jq -r 'select(.id == "33B1225950029")'

# json-only output for easy post-processing
mosquitto_sub -L mqtt://$MQTT_USERID:$MQTT_PASSWORD@localhost:11883/MQTT_ENY_NOW | jq -r 'select(.id == "33B1225950029") | "\(.id) \(.time) \(.zygsz)"'

# all power messages of a specific meter
mosquitto_sub -L mqtt://$MQTT_USERID:$MQTT_PASSWORD@localhost:11883/MQTT_RT_DATA | \
    jq -r 'select(.id == "33B1225950027") | "\(.id) \(.time) \(.zyggl)"'


