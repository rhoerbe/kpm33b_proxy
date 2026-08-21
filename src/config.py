"""Configuration loader and validation for kpm33b_proxy."""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

from src.transform import PER_PHASE_GROUPS

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
    upload_frequency_seconds_by_device: dict[str, int] | None = None
    expire_after_factor: float = 2.5
    exclude_device_ids: list[str] | None = None
    device_contexts: dict[str, str] | None = None
    per_phase_device_ids: list[str] | None = None
    per_phase_groups: list[str] = ["current", "power", "voltage"]
    duplicate_dict_max_length: int = 30

    @field_validator("expire_after_factor")
    @classmethod
    def validate_expire_after_factor(cls, v: float) -> float:
        if v <= 1.0:
            raise ValueError("expire_after_factor must be > 1.0, otherwise entities expire between publishes")
        return v

    @field_validator("per_phase_groups")
    @classmethod
    def validate_per_phase_groups(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(PER_PHASE_GROUPS)
        if unknown:
            raise ValueError(f"Unknown per_phase_groups {sorted(unknown)}. Allowed: {sorted(PER_PHASE_GROUPS)}")
        return v

    def upload_frequency_seconds_for(self, device_id: str) -> int:
        """Effective second-level upload interval for a meter (per-device override wins)."""
        overrides = self.upload_frequency_seconds_by_device
        if overrides and device_id in overrides:
            return overrides[device_id]
        return self.upload_frequency_seconds

    def per_phase_groups_for(self, device_id: str) -> list[str]:
        """Per-phase measurement groups published for a meter (empty if not enabled)."""
        if self.per_phase_device_ids and device_id in self.per_phase_device_ids:
            return list(self.per_phase_groups)
        return []


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
