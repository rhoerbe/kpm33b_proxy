"""Shared utilities for the RF bridge proxy."""

import re

_UMLAUT_MAP = str.maketrans({
    'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
    'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    'ß': 'ss',
})


def sanitise_topic_name(name: str) -> str:
    """Convert a friendly sensor name to a safe MQTT topic segment.

    Replaces German umlauts with ASCII equivalents, then replaces any
    remaining non-alphanumeric characters (except hyphen) with underscores,
    and collapses consecutive underscores.
    """
    name = name.translate(_UMLAUT_MAP)
    name = re.sub(r'[^A-Za-z0-9_-]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')
