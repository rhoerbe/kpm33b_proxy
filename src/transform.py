"""Data transformation for KPM33B meter messages.

Transforms raw meter JSON into simplified format per data_mapping.md.
"""

import logging

logger = logging.getLogger(__name__)


class IsendError(Exception):
    """Raised when isend field is not '1', indicating split data (not supported for KPM33B)."""


def _validate_isend(raw: dict) -> None:
    isend = raw.get("isend")
    if isend != "1":
        raise IsendError(f"isend={isend!r} — split data not implemented for KPM33B")


def transform_rt_data(raw: dict) -> dict:
    """Transform MQTT_RT_DATA (seconds-level) message.

    Returns dict with keys: id, time, active_power.
    Missing source tags produce None values.
    """
    _validate_isend(raw)
    return {
        "id": raw.get("id"),
        "time": raw.get("time"),
        "active_power": raw.get("zyggl"),
    }


def transform_eny_now(raw: dict) -> dict:
    """Transform MQTT_ENY_NOW (minutes-level) message.

    Returns dict with keys: id, time, active_energy.
    Missing source tags produce None values.
    """
    _validate_isend(raw)
    return {
        "id": raw.get("id"),
        "time": raw.get("time"),
        "active_energy": raw.get("zygsz"),
    }
