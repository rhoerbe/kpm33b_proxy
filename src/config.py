"""Configuration loader and validation for kpm33b_proxy."""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BrokerConfig(BaseModel):
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class InternalBrokerTopics(BaseModel):
    meter_seconds_data: str
    meter_minutes_data: str
    meter_settime: str
    meter_settime_ack: str


class CentralBrokerTopics(BaseModel):
    external_main_topic: str
    status_topic: str


class LoggingConfig(BaseModel):
    level: str = "INFO"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"Invalid log level '{v}'. Must be one of {allowed}")
        return v_upper


class MeterConfig(BaseModel):
    upload_frequency_seconds: int
    upload_frequency_minutes: int
    exclude_device_ids: list[str] | None = None


class AppConfig(BaseModel):
    internal_broker: BrokerConfig
    central_broker: BrokerConfig
    internal_broker_topics: InternalBrokerTopics
    central_broker_topics: CentralBrokerTopics
    logging: LoggingConfig = LoggingConfig()
    kpm33b_meters: MeterConfig


def load_config(config_path: Path | None = None) -> AppConfig:
    if config_path is None:
        config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open() as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)
