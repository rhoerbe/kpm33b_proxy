"""RF protocol decoding for Portisch AA B1 bucket frames.

Supports plug-in protocol definitions. New protocols are added by registering
a timing fingerprint and field layout without modifying the parsing core.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RATIO_TOLERANCE = 0.15


@dataclass
class DecodedFrame:
    """A fully decoded RF sensor frame."""
    protocol: str
    sof: int          # 4-bit start-of-frame marker
    device_id: int    # 8-bit rolling device ID
    battery_ok: bool
    tx_button: bool   # True = manual transmission triggered
    channel: int      # 1-based channel number (physical switch position)
    temperature: float  # °C, one decimal place
    humidity: int     # %RH
    raw_data: str = field(default="", repr=False)

    @property
    def device_id_hex(self) -> str:
        return f"0x{self.device_id:02X}"


@dataclass(frozen=True)
class ProtocolDef:
    """Timing-fingerprint-based protocol definition.

    Ratios characterize the relationship between pulse widths in the bucket table.
    gap_ratio  = gap1 / gap0    (expected ≈ 2.0 for nexus_compatible)
    sync_ratio = sync / gap0    (expected ≈ 4.8 for nexus_compatible)
    """
    name: str
    gap_ratio: float
    sync_ratio: float
    frame_bits: int


KNOWN_PROTOCOLS: list[ProtocolDef] = [
    ProtocolDef(
        name="nexus_compatible",
        gap_ratio=2.0,
        sync_ratio=4.8,
        frame_bits=36,
    ),
]


def _identify_protocol(buckets: list[int]) -> tuple[str | None, int, int, int]:
    """Match bucket timings against known protocols.

    Args:
        buckets: List of bucket durations in µs. Bucket 0 is the constant short
                 pulse (not present in bitstream); only buckets 1+ are considered.

    Returns:
        Tuple (protocol_name, sync_idx, gap0_idx, gap1_idx).
        All indices are -1 and protocol_name is None on no match.
    """
    # Need at least 3 data buckets beyond bucket 0
    data_buckets = [(i, d) for i, d in enumerate(buckets) if i > 0]
    if len(data_buckets) < 3:
        return None, -1, -1, -1

    data_buckets.sort(key=lambda x: x[1])
    gap0_idx, gap0_dur = data_buckets[0]
    gap1_idx, gap1_dur = data_buckets[1]
    sync_idx, sync_dur = data_buckets[2]

    if gap0_dur == 0:
        return None, -1, -1, -1

    actual_gap_ratio = gap1_dur / gap0_dur
    actual_sync_ratio = sync_dur / gap0_dur

    lo, hi = 1 - RATIO_TOLERANCE, 1 + RATIO_TOLERANCE
    for proto in KNOWN_PROTOCOLS:
        if (proto.gap_ratio * lo <= actual_gap_ratio <= proto.gap_ratio * hi and
                proto.sync_ratio * lo <= actual_sync_ratio <= proto.sync_ratio * hi):
            return proto.name, sync_idx, gap0_idx, gap1_idx

    return None, -1, -1, -1


def _bits_to_int(bits: list[int]) -> int:
    result = 0
    for b in bits:
        result = (result << 1) | b
    return result


def _decode_nexus_bits(bits: list[int], raw_data: str) -> DecodedFrame | None:
    """Decode a 36-bit Nexus-compatible frame.

    Field layout (bits 0–35):
      0–3   SOF marker (expected 0b0101)
      4–11  Device ID (random, rolls on battery swap)
      12    Battery OK (1 = OK)
      13    TX button pressed
      14–15 Channel (0=ch1, 1=ch2, 2=ch3)
      16–27 Temperature (signed 12-bit, ×0.1°C)
      28–35 Humidity (%RH)
    """
    if len(bits) != 36:
        logger.debug("Expected 36 bits for nexus_compatible, got %d", len(bits))
        return None

    sof = _bits_to_int(bits[0:4])
    device_id = _bits_to_int(bits[4:12])
    battery_ok = bool(bits[12])
    tx_button = bool(bits[13])
    channel_raw = _bits_to_int(bits[14:16])
    channel = channel_raw + 1  # 0b00 → ch1, 0b01 → ch2, 0b10 → ch3

    raw_temp = _bits_to_int(bits[16:28])
    if raw_temp >= 2048:  # signed 12-bit two's-complement
        raw_temp -= 4096
    temperature = raw_temp / 10.0

    humidity = _bits_to_int(bits[28:36])

    return DecodedFrame(
        protocol="nexus_compatible",
        sof=sof,
        device_id=device_id,
        battery_ok=battery_ok,
        tx_button=tx_button,
        channel=channel,
        temperature=temperature,
        humidity=humidity,
        raw_data=raw_data,
    )


def parse_rfraw_payload(raw_hex: str) -> DecodedFrame | None:
    """Parse a Portisch AA B1 bucket frame from a hex string.

    Expected format:
        AA B1 <num_buckets> [bucket_hi bucket_lo ...] <bitstream_hex> 55

    Decoding steps:
    1. Validate AA B1 header and end marker 55.
    2. Parse bucket count and durations.
    3. Identify protocol family from timing ratios.
    4. Extract bits: each bitstream byte's high nibble is the bucket index;
       low nibble is always 0x8 (encoding artifact, ignored).
    5. Collect bits between sync markers; decode the first complete frame.

    Returns DecodedFrame on success, None on any parse or decode failure.
    """
    tokens = raw_hex.upper().split()

    if len(tokens) < 5 or tokens[0] != "AA" or tokens[1] != "B1":
        logger.debug("Not an AA B1 frame: %.60s", raw_hex)
        return None

    try:
        num_buckets = int(tokens[2], 16)
    except ValueError:
        logger.debug("Cannot parse bucket count: %s", tokens[2])
        return None

    # Minimum tokens: AA B1 <count> + num_buckets + bitstream + 55
    min_tokens = 3 + num_buckets + 2
    if len(tokens) < min_tokens:
        logger.debug("Frame too short (%d tokens, need %d): %.60s", len(tokens), min_tokens, raw_hex)
        return None

    try:
        buckets = [int(tokens[3 + i], 16) for i in range(num_buckets)]
    except ValueError:
        logger.debug("Cannot parse bucket durations: %s", tokens[3:3 + num_buckets])
        return None

    bitstream_hex = tokens[3 + num_buckets]
    end_marker = tokens[3 + num_buckets + 1]

    if end_marker != "55":
        logger.debug("Missing end marker 55, got: %s", end_marker)
        return None

    if len(bitstream_hex) % 2 != 0:
        logger.debug("Odd-length bitstream: %s", bitstream_hex)
        return None

    try:
        bitstream_bytes = [int(bitstream_hex[i:i + 2], 16) for i in range(0, len(bitstream_hex), 2)]
    except ValueError:
        logger.debug("Invalid bitstream hex: %.60s", bitstream_hex)
        return None

    protocol_name, sync_idx, gap0_idx, gap1_idx = _identify_protocol(buckets)
    if protocol_name is None:
        logger.debug("Unknown protocol fingerprint; buckets=%s for: %.80s", buckets, raw_hex)
        return None

    proto_def = next(p for p in KNOWN_PROTOCOLS if p.name == protocol_name)

    # Collect bits between sync markers; return the first complete frame
    in_frame = False
    current_bits: list[int] = []

    for byte_val in bitstream_bytes:
        idx = byte_val >> 4
        if idx == sync_idx:
            if in_frame and len(current_bits) == proto_def.frame_bits:
                break  # first complete frame collected
            in_frame = True
            current_bits = []
        elif in_frame:
            if idx == gap0_idx:
                current_bits.append(0)
            elif idx == gap1_idx:
                current_bits.append(1)
            else:
                logger.debug("Unknown bucket index %d in bitstream", idx)

    if len(current_bits) != proto_def.frame_bits:
        logger.debug(
            "Incomplete frame: got %d bits, expected %d: %.80s",
            len(current_bits), proto_def.frame_bits, raw_hex,
        )
        return None

    frame = _decode_nexus_bits(current_bits, raw_hex)
    return frame
