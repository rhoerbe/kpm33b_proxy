"""Sensor registry for 433 MHz RF bridge proxy.

Maps (protocol, channel) tuples to friendly sensor names defined in sensors.yaml.
Handles rolling device IDs (change on battery swap) via the DeadSensorRegistry
heuristic for sensors that lack a physical channel selector (all on channel 0).
"""

import logging
import time
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class SensorRegistry:
    """Loads sensors.yaml and provides sensor lookup and ID tracking.

    Stable key: (protocol_family, channel). Channel is set by a physical switch
    and survives battery replacement, making it a reliable identifier.
    For sensors where channel is always 0 (no physical selector), fall back to
    DeadSensorRegistry migration logic.
    """

    def __init__(self, sensors_path: Path, sensor_timeout_seconds: int = 3600):
        self._path = sensors_path
        self._sensor_timeout_seconds = sensor_timeout_seconds
        self._sensors: dict = {}
        self._last_seen: dict[str, float] = {}   # friendly_name → timestamp
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("sensors.yaml not found at %s — no sensors configured", self._path)
            self._sensors = {}
            return
        with self._path.open() as f:
            data = yaml.safe_load(f) or {}
        self._sensors = data.get("sensors", {})
        logger.info("Loaded %d sensors from %s", len(self._sensors), self._path)

    def _save(self) -> None:
        with self._path.open("w") as f:
            yaml.dump({"sensors": self._sensors}, f, default_flow_style=False, allow_unicode=True)

    def lookup(self, protocol: str, channel: int) -> Optional[str]:
        """Return the friendly name for a sensor by (protocol, channel), or None."""
        for name, cfg in self._sensors.items():
            proto_match = cfg.get("protocol") in (protocol, "auto")
            if proto_match and cfg.get("channel") == channel:
                return name
        return None

    def update_last_seen(self, friendly_name: str, device_id_hex: str) -> bool:
        """Update last_seen_id in sensors.yaml if it changed. Returns True if updated."""
        self._last_seen[friendly_name] = time.time()
        cfg = self._sensors.get(friendly_name)
        if cfg is None:
            return False
        if cfg.get("last_seen_id") != device_id_hex:
            cfg["last_seen_id"] = device_id_hex
            self._save()
            logger.info("Updated last_seen_id for '%s' to %s", friendly_name, device_id_hex)
            return True
        return False

    def register_new_sensor(self, friendly_name: str, protocol: str, channel: int, device_id_hex: str) -> None:
        """Add a migrated sensor entry to sensors.yaml."""
        self._sensors[friendly_name] = {
            "protocol": protocol,
            "channel": channel,
            "last_seen_id": device_id_hex,
        }
        self._last_seen[friendly_name] = time.time()
        self._save()
        logger.info("Registered migrated sensor '%s' (proto=%s, ch=%d, id=%s)",
                    friendly_name, protocol, channel, device_id_hex)

    def collect_dead_sensors(self) -> dict[str, dict]:
        """Return sensors that have not been heard from within sensor_timeout_seconds."""
        now = time.time()
        dead: dict[str, dict] = {}
        for name, cfg in self._sensors.items():
            last_seen = self._last_seen.get(name)
            if last_seen is not None and (now - last_seen) > self._sensor_timeout_seconds:
                dead[name] = {
                    "protocol": cfg.get("protocol", ""),
                    "channel": cfg.get("channel", 0),
                    "last_seen": last_seen,
                }
        return dead


class DeadSensorRegistry:
    """Tracks sensors that have gone silent and tries to re-map them on new IDs.

    Used only for sensors where channel == 0 (no physical channel selector),
    as the (protocol, channel) key is ambiguous for those sensors.
    """

    def __init__(self, migration_window_seconds: int = 900):
        self._migration_window_seconds = migration_window_seconds
        self._dead: dict[str, dict] = {}  # friendly_name → {protocol, channel, last_seen}

    def add(self, friendly_name: str, protocol: str, channel: int, last_seen: float) -> None:
        self._dead[friendly_name] = {"protocol": protocol, "channel": channel, "last_seen": last_seen}

    def check_for_battery_swap(
        self,
        new_hex_id: str,
        new_protocol: str,
        new_channel: int,
    ) -> Optional[str]:
        """Find a dead sensor that matches protocol and channel within migration window.

        Returns the friendly name of the unique match, or None if zero or multiple matches.
        """
        now = time.time()
        candidates = []
        for name, data in self._dead.items():
            time_since_death = now - data["last_seen"]
            if time_since_death < self._migration_window_seconds:
                if data["protocol"] == new_protocol and data["channel"] == new_channel:
                    candidates.append(name)
        if len(candidates) == 1:
            matched = candidates[0]
            del self._dead[matched]
            return matched
        return None


class Deduplicator:
    """Suppress repeated frames from RF sensors (3–5 identical bursts per measurement).

    Two filters:
    1. Deduplication: drops frames where (device_id, temp, humidity) matches the previous
       frame from the same (protocol, channel) within dedup_window_seconds.
    2. Outlier rejection: drops frames where temperature deviates by more than
       outlier_temp_delta from the previous reading.
    """

    def __init__(self, dedup_window_seconds: int = 30, outlier_temp_delta: float = 10.0):
        self._window = dedup_window_seconds
        self._outlier_delta = outlier_temp_delta
        # key: (protocol, channel) → {device_id, temperature, humidity, timestamp}
        self._last: dict[tuple, dict] = {}

    def is_duplicate_or_outlier(
        self,
        protocol: str,
        channel: int,
        device_id: int,
        temperature: float,
        humidity: int,
    ) -> bool:
        """Return True if the frame should be suppressed."""
        key = (protocol, channel)
        now = time.time()
        prev = self._last.get(key)

        if prev is not None:
            within_window = (now - prev["timestamp"]) < self._window
            same_reading = (
                prev["device_id"] == device_id
                and prev["temperature"] == temperature
                and prev["humidity"] == humidity
            )
            if within_window and same_reading:
                logger.debug("Suppressing duplicate frame proto=%s ch=%d", protocol, channel)
                return True

            # Outlier check (only against a previous reading, regardless of window)
            if abs(temperature - prev["temperature"]) > self._outlier_delta:
                logger.warning(
                    "Outlier temperature rejected: %.1f°C vs previous %.1f°C (delta > %.1f) on ch=%d",
                    temperature, prev["temperature"], self._outlier_delta, channel,
                )
                return True

        self._last[key] = {
            "device_id": device_id,
            "temperature": temperature,
            "humidity": humidity,
            "timestamp": now,
        }
        return False
