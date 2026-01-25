## KPM33B Energy Meter Integration into EMA and Smart Home Systems (like Home Assistant)

This project delivers a MQTT "proxy" to read KPM33B meter data in a filtered and simplified format. 
It features following functions:
- Work as a MQTT bridge
- Publish messages under a separate topic per device, and a common top-level topic
- Creates MQTT Message Profile limiting data to active power and energy, import only. (no reactive/apparent measurements)
- Provides an interface to configure the KPM33B device with:
  - Synchronization time with system time (assuming that system time is synced with an NTP pool)
  - setting upload frequency (second/minute) from a config file 



