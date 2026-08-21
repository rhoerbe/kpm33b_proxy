"""Data transformation for KPM33B meter messages.

Transforms raw meter JSON into simplified format per data_mapping.md.
"""

import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Optional per-phase measurements of MQTT_RT_DATA, grouped by quantity.
# Each group maps the raw COMPERE tag to the output field name.
PER_PHASE_GROUPS: dict[str, dict[str, str]] = {
    "current": {"ia": "current_l1", "ib": "current_l2", "ic": "current_l3"},
    "power": {"pa": "active_power_l1", "pb": "active_power_l2", "pc": "active_power_l3"},
    "voltage": {"ua": "voltage_l1", "ub": "voltage_l2", "uc": "voltage_l3"},
    "power_factor": {
        "pfa": "power_factor_l1",
        "pfb": "power_factor_l2",
        "pfc": "power_factor_l3",
        "zglys": "power_factor",
    },
}


class IsendError(Exception):
    """Raised when isend field is not '1', indicating split data (not supported for KPM33B)."""


def _validate_isend(raw: dict) -> None:
    isend = raw.get("isend")
    if isend != "1":
        raise IsendError(f"isend={isend!r} — split data not implemented for KPM33B")


def transform_rt_data(raw: dict, per_phase_groups: Sequence[str] = ()) -> dict:
    """Transform MQTT_RT_DATA (seconds-level) message.

    Returns dict with keys: id, time, active_power. Missing source tags produce
    None values.

    Args:
        raw: The raw MQTT_RT_DATA message
        per_phase_groups: Names of PER_PHASE_GROUPS to append to the payload.
            Empty (the default) keeps the payload byte-identical to the
            id/time/active_power profile consumed by existing subscribers.
    """
    _validate_isend(raw)
    result = {
        "id": raw.get("id"),
        "time": raw.get("time"),
        "active_power": raw.get("zyggl"),
    }
    for group in per_phase_groups:
        for source_tag, output_name in PER_PHASE_GROUPS[group].items():
            result[output_name] = raw.get(source_tag)
    return result


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
