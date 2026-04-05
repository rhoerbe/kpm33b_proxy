"""Unit tests for src/rfbridge/sensor_registry.py."""

import time
from pathlib import Path

import pytest
import yaml

from src.rfbridge.sensor_registry import DeadSensorRegistry, Deduplicator, SensorRegistry


@pytest.fixture
def sensors_yaml(tmp_path: Path) -> Path:
    data = {
        "sensors": {
            "living_room": {"protocol": "nexus_compatible", "channel": 1, "last_seen_id": None},
            "bedroom": {"protocol": "nexus_compatible", "channel": 2, "last_seen_id": None},
        }
    }
    path = tmp_path / "sensors.yaml"
    path.write_text(yaml.dump(data))
    return path


@pytest.fixture
def registry(sensors_yaml: Path) -> SensorRegistry:
    return SensorRegistry(sensors_yaml, sensor_timeout_seconds=3600)


class TestSensorRegistryLookup:
    def test_lookup_by_protocol_and_channel(self, registry):
        assert registry.lookup("nexus_compatible", 1) == "living_room"
        assert registry.lookup("nexus_compatible", 2) == "bedroom"

    def test_lookup_unknown_channel(self, registry):
        assert registry.lookup("nexus_compatible", 3) is None

    def test_lookup_unknown_protocol(self, registry):
        assert registry.lookup("foo_protocol", 1) is None

    def test_lookup_auto_protocol_matches_any(self, tmp_path):
        data = {"sensors": {"garage": {"protocol": "auto", "channel": 1, "last_seen_id": None}}}
        path = tmp_path / "sensors.yaml"
        path.write_text(yaml.dump(data))
        reg = SensorRegistry(path)
        assert reg.lookup("nexus_compatible", 1) == "garage"
        assert reg.lookup("some_other_proto", 1) == "garage"

    def test_missing_sensors_yaml(self, tmp_path):
        reg = SensorRegistry(tmp_path / "nonexistent.yaml")
        assert reg.lookup("nexus_compatible", 1) is None


class TestSensorRegistryUpdateLastSeen:
    def test_update_saves_new_id(self, registry, sensors_yaml):
        changed = registry.update_last_seen("living_room", "0x84")
        assert changed is True
        with sensors_yaml.open() as f:
            data = yaml.safe_load(f)
        assert data["sensors"]["living_room"]["last_seen_id"] == "0x84"

    def test_no_save_if_id_unchanged(self, registry, sensors_yaml):
        registry.update_last_seen("living_room", "0x84")
        mtime_before = sensors_yaml.stat().st_mtime
        changed = registry.update_last_seen("living_room", "0x84")
        assert changed is False
        assert sensors_yaml.stat().st_mtime == mtime_before

    def test_update_unknown_sensor(self, registry):
        changed = registry.update_last_seen("unknown_sensor", "0x01")
        assert changed is False


class TestSensorRegistryDeadSensors:
    def test_no_dead_sensors_initially(self, registry):
        registry.update_last_seen("living_room", "0x84")
        dead = registry.collect_dead_sensors()
        assert "living_room" not in dead

    def test_sensor_becomes_dead_after_timeout(self, tmp_path):
        data = {"sensors": {"old_sensor": {"protocol": "nexus_compatible", "channel": 1, "last_seen_id": "0x01"}}}
        path = tmp_path / "sensors.yaml"
        path.write_text(yaml.dump(data))
        reg = SensorRegistry(path, sensor_timeout_seconds=1)
        reg.update_last_seen("old_sensor", "0x01")
        time.sleep(1.1)
        dead = reg.collect_dead_sensors()
        assert "old_sensor" in dead


class TestDeadSensorRegistry:
    def test_single_candidate_returns_name(self):
        dsr = DeadSensorRegistry(migration_window_seconds=900)
        dsr.add("living_room", "nexus_compatible", 1, time.time())
        result = dsr.check_for_battery_swap("0xC2", "nexus_compatible", 1)
        assert result == "living_room"

    def test_matched_sensor_removed_from_registry(self):
        dsr = DeadSensorRegistry(migration_window_seconds=900)
        dsr.add("living_room", "nexus_compatible", 1, time.time())
        dsr.check_for_battery_swap("0xC2", "nexus_compatible", 1)
        assert dsr.check_for_battery_swap("0xC3", "nexus_compatible", 1) is None

    def test_multiple_candidates_returns_none(self):
        dsr = DeadSensorRegistry(migration_window_seconds=900)
        dsr.add("sensor_a", "nexus_compatible", 1, time.time())
        dsr.add("sensor_b", "nexus_compatible", 1, time.time())
        result = dsr.check_for_battery_swap("0xC2", "nexus_compatible", 1)
        assert result is None

    def test_expired_candidate_not_matched(self):
        dsr = DeadSensorRegistry(migration_window_seconds=1)
        dsr.add("living_room", "nexus_compatible", 1, time.time() - 2)
        result = dsr.check_for_battery_swap("0xC2", "nexus_compatible", 1)
        assert result is None

    def test_protocol_mismatch_not_matched(self):
        dsr = DeadSensorRegistry(migration_window_seconds=900)
        dsr.add("living_room", "nexus_compatible", 1, time.time())
        result = dsr.check_for_battery_swap("0xC2", "other_protocol", 1)
        assert result is None

    def test_channel_mismatch_not_matched(self):
        dsr = DeadSensorRegistry(migration_window_seconds=900)
        dsr.add("living_room", "nexus_compatible", 1, time.time())
        result = dsr.check_for_battery_swap("0xC2", "nexus_compatible", 2)
        assert result is None


class TestDeduplicator:
    def test_first_reading_passes(self):
        dedup = Deduplicator(dedup_window_seconds=30)
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42) is False

    def test_immediate_duplicate_suppressed(self):
        dedup = Deduplicator(dedup_window_seconds=30)
        dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42)
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42) is True

    def test_different_channel_not_duplicate(self):
        dedup = Deduplicator(dedup_window_seconds=30)
        dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42)
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 2, 0x84, 25.0, 42) is False

    def test_changed_temperature_not_duplicate(self):
        dedup = Deduplicator(dedup_window_seconds=30)
        dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42)
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.1, 42) is False

    def test_outlier_temperature_suppressed(self):
        dedup = Deduplicator(dedup_window_seconds=30, outlier_temp_delta=10.0)
        dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 20.0, 42)
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 35.0, 42) is True

    def test_within_outlier_threshold_passes(self):
        dedup = Deduplicator(dedup_window_seconds=30, outlier_temp_delta=10.0)
        dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 20.0, 42)
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x85, 29.9, 42) is False

    def test_duplicate_after_window_expires(self):
        dedup = Deduplicator(dedup_window_seconds=0)  # zero-length window
        dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42)
        time.sleep(0.01)
        # Same reading after window: should not be suppressed
        assert dedup.is_duplicate_or_outlier("nexus_compatible", 1, 0x84, 25.0, 42) is False
