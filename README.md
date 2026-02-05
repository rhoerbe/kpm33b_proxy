## KPM33B Energy Meter Integration into EMA and Smart Home Systems (like Home Assistant)

This project delivers a MQTT "proxy" to read KPM33B meter data in a filtered and simplified format. 
The KPM33B is an energy meter from Compere (https://comperepower.com).

Motivation: The KPM33B publishes fairly complex JSON data at fixed root topics. 
To simplify the integration into smarthome solutions the messages are restructured.  
The proxy features following functions:
- Work as a MQTT bridge
- Publish messages under a separate topic per device, and a common top-level topic
- Creates MQTT Message Profile limiting data to active power and energy, import only. (no reactive/apparent measurements)
- Provides an interface to configure the KPM33B device to set the upload frequency (second/minute) from a config file. 
- Provides Home Assistant Auto-Discovery Messages (in topic /homeassitant/sensor/)
