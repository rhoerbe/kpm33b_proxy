"""Unit tests for src/config.py."""

import textwrap
from pathlib import Path

import pytest
import yaml

from src.config import AppConfig, load_config


@pytest.fixture
def valid_config_dict():
    return {
        "internal_broker": {"host": "0.0.0.0", "port": 11883},
        "central_broker": {"host": "10.4.4.17", "port": 1883},
        "internal_broker_topics": {
            "meter_seconds_data": "MQTT_RT_DATA",
            "meter_minutes_data": "MQTT_ENY_NOW",
            "meter_settime": "MQTT_COMMOD_SET_",
            "meter_settime_ack": "MQTT_COMMOD_SET_REP",
        },
        "central_broker_topics": {
            "external_main_topic": "kpm33b",
            "status_topic": "kpm33b/status",
        },
        "logging": {"level": "INFO", "file": "/tmp/test_kpm33b.log"},
        "kpm33b_meters": {"upload_frequency_seconds": 5, "upload_frequency_minutes": 1},
    }


def test_load_config_from_project_root():
    """config.yaml in project root loads without error."""
    config = load_config()
    assert config.internal_broker.port == 11883
    assert config.central_broker.host == "10.4.4.17"
    assert config.internal_broker_topics.meter_seconds_data == "MQTT_RT_DATA"
    assert config.central_broker_topics.external_main_topic == "kpm33b"


def test_load_config_from_explicit_path(tmp_path, valid_config_dict):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(valid_config_dict))
    config = load_config(config_file)
    assert config.kpm33b_meters.upload_frequency_seconds == 5


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.yaml"))


def test_invalid_log_level(tmp_path, valid_config_dict):
    valid_config_dict["logging"]["level"] = "VERBOSE"
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(valid_config_dict))
    with pytest.raises(Exception):
        load_config(config_file)


def test_missing_required_field(tmp_path, valid_config_dict):
    del valid_config_dict["internal_broker"]
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(valid_config_dict))
    with pytest.raises(Exception):
        load_config(config_file)


def test_app_config_direct(valid_config_dict):
    config = AppConfig(**valid_config_dict)
    assert config.logging.level == "INFO"
    assert config.central_broker.port == 1883
