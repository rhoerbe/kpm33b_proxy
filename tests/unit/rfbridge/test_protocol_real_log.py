"""Integration-style tests for protocol.py using real Tasmota RF bridge log data.

Tests run the decoder against every RESULT message captured in tests/test_msg/433rfbridge.log
and validate decode counts, sensor identification, and reading consistency.
"""

import json
import re
from pathlib import Path

import pytest

from src.rfbridge.protocol import parse_rfraw_payload

LOG_PATH = Path(__file__).resolve().parents[3] / "tests/test_msg/433rfbridge.log"


def _extract_rfraw_entries(log_path: Path) -> list[tuple[int, str]]:
    """Return (line_number, raw_hex) for every RfRaw.Data entry in the log."""
    entries = []
    for lineno, line in enumerate(log_path.read_text().splitlines(), 1):
        m = re.search(r'"RfRaw":\{"Data":"([^"]+)"\}', line)
        if m:
            entries.append((lineno, m.group(1)))
    return entries


@pytest.fixture(scope="module")
def decoded_frames():
    """Parse the full log file; return list of (lineno, frame_or_None)."""
    if not LOG_PATH.exists():
        pytest.skip(f"Test log file not present: {LOG_PATH}")
    entries = _extract_rfraw_entries(LOG_PATH)
    return [(lineno, parse_rfraw_payload(raw)) for lineno, raw in entries]


class TestRealLogDecodeRate:
    def test_total_rfraw_messages(self, decoded_frames):
        # 75 RESULT messages in the log (some are from other devices, noise, or partial frames)
        assert len(decoded_frames) == 75

    def test_decoded_count(self, decoded_frames):
        decoded = [f for _, f in decoded_frames if f is not None]
        assert len(decoded) == 43

    def test_rejected_count(self, decoded_frames):
        rejected = [f for _, f in decoded_frames if f is None]
        assert len(rejected) == 32


class TestRealLogSensorIdentification:
    def test_exactly_two_channels(self, decoded_frames):
        channels = {f.channel for _, f in decoded_frames if f is not None}
        assert channels == {1, 2}

    def test_channel_1_device_id(self, decoded_frames):
        ids = {f.device_id for _, f in decoded_frames if f is not None and f.channel == 1}
        assert ids == {0x84}, f"Unexpected device IDs for ch=1: {ids}"

    def test_channel_2_device_id(self, decoded_frames):
        ids = {f.device_id for _, f in decoded_frames if f is not None and f.channel == 2}
        assert ids == {0x00}, f"Unexpected device IDs for ch=2: {ids}"

    def test_all_battery_ok(self, decoded_frames):
        low_battery = [f for _, f in decoded_frames if f is not None and not f.battery_ok]
        assert low_battery == []


class TestRealLogReadingConsistency:
    def test_channel_1_temperature_range(self, decoded_frames):
        temps = [f.temperature for _, f in decoded_frames if f is not None and f.channel == 1]
        for t in temps:
            assert 25.0 <= t <= 25.2, f"Unexpected temperature {t}°C on ch=1"

    def test_channel_2_temperature_range(self, decoded_frames):
        temps = [f.temperature for _, f in decoded_frames if f is not None and f.channel == 2]
        for t in temps:
            assert 24.8 <= t <= 25.1, f"Unexpected temperature {t}°C on ch=2"

    def test_channel_1_humidity(self, decoded_frames):
        humidities = {f.humidity for _, f in decoded_frames if f is not None and f.channel == 1}
        assert humidities == {42}

    def test_channel_2_humidity(self, decoded_frames):
        humidities = {f.humidity for _, f in decoded_frames if f is not None and f.channel == 2}
        assert humidities == {41}

    def test_protocol_is_nexus_compatible(self, decoded_frames):
        protocols = {f.protocol for _, f in decoded_frames if f is not None}
        assert protocols == {"nexus_compatible"}


class TestRealLogRejectedFrameClasses:
    """Verify that specific known-noise message types are correctly rejected."""

    def test_3_bucket_frames_rejected(self):
        # 3-bucket frames have no sync bucket; cannot identify protocol
        three_bucket = [
            "AA B1 03 01D9 0765 0EE3 281818 55",
            "AA B1 03 021B 0779 0F7E 28181818 55",
        ]
        for raw in three_bucket:
            assert parse_rfraw_payload(raw) is None, f"Should be rejected: {raw}"

    def test_6_bucket_frames_rejected(self):
        # 6-bucket frames are a different device protocol, not nexus_compatible
        six_bucket = (
            "AA B1 06 03C3 0228 1E1A 0F99 077C 3D1C "
            "58080808092939393949494939494949394949493949493949393939393939394939493949394949393949494939 55"
        )
        assert parse_rfraw_payload(six_bucket) is None

    def test_short_bitstream_4_bucket_rejected(self):
        # Partial capture — too few bits to form a 36-bit frame
        assert parse_rfraw_payload("AA B1 04 020C 072B 0FE5 0F86 381828 55") is None

    def test_line36_partial_nexus_rejected(self):
        # Bucket timings match nexus_compatible but bitstream is only 3 bytes
        assert parse_rfraw_payload("AA B1 04 01D7 2327 0766 0ED2 381828 55") is None
