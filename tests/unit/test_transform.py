"""Unit tests for src/transform.py."""

import json
from pathlib import Path

import pytest

from src.transform import PER_PHASE_GROUPS, IsendError, transform_eny_now, transform_rt_data

TEST_MSG_DIR = Path(__file__).resolve().parent.parent / "test_msg"


def _load_fixture(name: str) -> dict:
    return json.loads((TEST_MSG_DIR / name).read_text())


class TestTransformRtData:
    def test_valid_message(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        result = transform_rt_data(raw)
        assert result["id"] == "33B1225950027"
        assert result["time"] == "20260112163900"
        assert result["active_power"] == 6.6905

    def test_missing_zyggl(self):
        raw = _load_fixture("MQTT_RT_DATA_missing_data.json")
        result = transform_rt_data(raw)
        assert result["id"] == "33B1225950027"
        assert result["time"] == "20260112163900"
        assert result["active_power"] is None

    def test_isend_not_1_raises(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        raw["isend"] = "0"
        with pytest.raises(IsendError):
            transform_rt_data(raw)

    def test_isend_missing_raises(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        del raw["isend"]
        with pytest.raises(IsendError):
            transform_rt_data(raw)

    def test_output_keys(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        result = transform_rt_data(raw)
        assert set(result.keys()) == {"id", "time", "active_power"}


class TestTransformRtDataPerPhase:
    """Per-phase extension added in issue #12."""

    def test_current_group(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        result = transform_rt_data(raw, ["current"])
        assert result["current_l1"] == raw["ia"]
        assert result["current_l2"] == raw["ib"]
        assert result["current_l3"] == raw["ic"]

    def test_power_and_voltage_groups(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        result = transform_rt_data(raw, ["power", "voltage"])
        assert result["active_power_l1"] == raw["pa"]
        assert result["active_power_l2"] == raw["pb"]
        assert result["active_power_l3"] == raw["pc"]
        assert result["voltage_l1"] == raw["ua"]
        assert result["voltage_l2"] == raw["ub"]
        assert result["voltage_l3"] == raw["uc"]

    def test_power_factor_group_includes_total(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        result = transform_rt_data(raw, ["power_factor"])
        assert result["power_factor_l1"] == raw["pfa"]
        assert result["power_factor"] == raw["zglys"]

    def test_base_profile_unchanged(self):
        """Existing subscribers keep seeing id/time/active_power with the same values."""
        raw = _load_fixture("MQTT_RT_DATA.json")
        base = transform_rt_data(raw)
        extended = transform_rt_data(raw, list(PER_PHASE_GROUPS))
        for key, value in base.items():
            assert extended[key] == value

    def test_empty_groups_is_base_profile(self):
        raw = _load_fixture("MQTT_RT_DATA.json")
        assert set(transform_rt_data(raw, []).keys()) == {"id", "time", "active_power"}

    def test_missing_tags_produce_none(self):
        raw = _load_fixture("MQTT_RT_DATA_missing_data.json")
        for tag in ("ia", "ib", "ic"):
            raw.pop(tag, None)
        result = transform_rt_data(raw, ["current"])
        assert result["current_l1"] is None
        assert result["current_l2"] is None
        assert result["current_l3"] is None

    def test_all_group_fields_are_unique(self):
        fields = [field for group in PER_PHASE_GROUPS.values() for field in group.values()]
        assert len(fields) == len(set(fields))
        assert "active_power" not in fields


class TestTransformEnyNow:
    def test_valid_message(self):
        raw = _load_fixture("MQTT_ENY_NOW.json")
        result = transform_eny_now(raw)
        assert result["id"] == "33B1225950027"
        assert result["time"] == "20260117211500"
        assert result["active_energy"] == 163.486

    def test_missing_zygsz(self):
        raw = _load_fixture("MQTT_ENY_NOW_missing_data.json")
        result = transform_eny_now(raw)
        assert result["id"] == "33B1225950027"
        assert result["time"] == "20260117211500"
        assert result["active_energy"] is None

    def test_isend_not_1_raises(self):
        raw = _load_fixture("MQTT_ENY_NOW.json")
        raw["isend"] = "2"
        with pytest.raises(IsendError):
            transform_eny_now(raw)

    def test_output_keys(self):
        raw = _load_fixture("MQTT_ENY_NOW.json")
        result = transform_eny_now(raw)
        assert set(result.keys()) == {"id", "time", "active_energy"}
