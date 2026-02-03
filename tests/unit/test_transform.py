"""Unit tests for src/transform.py."""

import json
from pathlib import Path

import pytest

from src.transform import IsendError, transform_eny_now, transform_rt_data

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
