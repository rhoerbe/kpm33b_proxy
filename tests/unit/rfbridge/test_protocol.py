"""Unit tests for src/rfbridge/protocol.py."""

import pytest

from src.rfbridge.protocol import (
    DecodedFrame,
    _identify_protocol,
    parse_rfraw_payload,
)

# Sample from issue #9 — T=25.0°C, H=42%, battery OK, channel 1, device_id=0x84
SAMPLE_RFRAW = (
    "AA B1 04 0211 075A 0ECF 232D "
    "38182818282818181818281818281818181818181828282828281828181818281828182818 55"
)


class TestIdentifyProtocol:
    def test_nexus_compatible_ratios(self):
        # buckets: 529, 1882, 3791, 9005 (indices 0..3)
        buckets = [0x0211, 0x075A, 0x0ECF, 0x232D]
        name, sync_idx, gap0_idx, gap1_idx = _identify_protocol(buckets)
        assert name == "nexus_compatible"
        assert sync_idx == 3
        assert gap0_idx == 1
        assert gap1_idx == 2

    def test_unknown_protocol(self):
        # Ratios deliberately wrong
        buckets = [100, 200, 300, 400]
        name, *_ = _identify_protocol(buckets)
        assert name is None

    def test_too_few_buckets(self):
        name, *_ = _identify_protocol([100, 200])
        assert name is None

    def test_gap0_is_zero(self):
        buckets = [0, 0, 200, 1000]
        name, *_ = _identify_protocol(buckets)
        assert name is None


class TestParseRfrawPayload:
    def test_sample_payload_temperature(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert frame.temperature == 25.0

    def test_sample_payload_humidity(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert frame.humidity == 42

    def test_sample_payload_battery_ok(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert frame.battery_ok is True

    def test_sample_payload_channel(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert frame.channel == 1

    def test_sample_payload_device_id(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert frame.device_id == 0x84
        assert frame.device_id_hex == "0x84"

    def test_sample_payload_protocol(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert frame.protocol == "nexus_compatible"

    def test_non_aab1_frame_ignored(self):
        assert parse_rfraw_payload("AA B0 04 0211 55") is None

    def test_empty_string(self):
        assert parse_rfraw_payload("") is None

    def test_malformed_hex(self):
        assert parse_rfraw_payload("AA B1 04 ZZZZ 075A 0ECF 232D DEADBEEF 55") is None

    def test_missing_end_marker(self):
        payload = "AA B1 04 0211 075A 0ECF 232D 38182818 FF"
        assert parse_rfraw_payload(payload) is None

    def test_raw_data_preserved(self):
        frame = parse_rfraw_payload(SAMPLE_RFRAW)
        assert frame is not None
        assert "AA B1" in frame.raw_data

    def test_unknown_protocol_returns_none(self):
        # Swap bucket durations to produce wrong ratios
        payload = "AA B1 04 0100 0110 0120 0130 38182818 55"
        assert parse_rfraw_payload(payload) is None


class TestNegativeTemperature:
    def _make_frame_with_temp(self, temp_raw: int) -> DecodedFrame | None:
        """Build a synthetic 36-bit nexus frame and round-trip through the parser."""
        from src.rfbridge.protocol import _decode_nexus_bits
        # SOF=0101, device_id=0x01, battery=1, tx=0, ch=00
        # temperature = temp_raw (12 bits), humidity = 50
        bits = list(map(int, "0101"))                              # SOF
        bits += list(map(int, f"{0x01:08b}"))                     # device_id
        bits += [1, 0]                                             # battery OK, no tx
        bits += [0, 0]                                             # channel 0 → ch1
        bits += [(temp_raw >> (11 - i)) & 1 for i in range(12)]   # temperature
        bits += list(map(int, f"{50:08b}"))                        # humidity
        return _decode_nexus_bits(bits, "synthetic")

    def test_positive_temperature(self):
        frame = self._make_frame_with_temp(250)
        assert frame is not None
        assert frame.temperature == 25.0

    def test_negative_temperature(self):
        # -5.0°C → raw = 4096 - 50 = 4046 (0xFCE)
        raw = 4096 - 50
        frame = self._make_frame_with_temp(raw)
        assert frame is not None
        assert frame.temperature == pytest.approx(-5.0, abs=0.01)

    def test_zero_temperature(self):
        frame = self._make_frame_with_temp(0)
        assert frame is not None
        assert frame.temperature == 0.0
