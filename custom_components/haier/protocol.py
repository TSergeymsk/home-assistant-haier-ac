"""Binary protocol for Haier AC units (mirrors bstuff/haier-ac-remote)."""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

PREFIX: bytes = b"\xff\xff"
CMD_CONTROL: int = 0x6D
CMD_STATUS: int = 0x6D

# Payload/command layout follows the original TS library:
#   0x6D <flags> <power> <mode> <temp> <fan> ...
SET_FLAGS_QUERY: int = 0x00
SET_FLAGS_CONTROL: int = 0x01

MIN_TEMP: int = 16
MAX_TEMP: int = 30


class ProtocolError(Exception):
    """Raised when a Haier protocol frame is malformed or fails checksum."""


def calculate_checksum(payload: bytes) -> int:
    """Checksum per bstuff/haier-ac-remote.

    The original computes ((sum(all bytes incl. 0xffff) - 2*0xff) & 0xff),
    which algebraically reduces to (sum(bytes after prefix) & 0xff).
    """
    total = sum(PREFIX) + sum(payload)
    return (total - 2 * 0xFF) & 0xFF


def extract_frames(buffer: bytearray) -> tuple[list[bytes], bytearray]:
    """Extract complete 0xffff-framed packets from a raw TCP byte buffer.

    Returns (complete_frames, remaining_buffer). Garbage before PREFIX is
    dropped; a trailing partial 0xff is kept in case the prefix is split
    across two TCP reads. Incomplete frames remain in the buffer.
    """
    frames: list[bytes] = []
    while True:
        start = buffer.find(PREFIX)
        if start < 0:
            keep = 1 if buffer.endswith(b"\xff") else 0
            if len(buffer) > keep:
                _LOGGER.debug("Dropping %d non-frame bytes", len(buffer) - keep)
                del buffer[: len(buffer) - keep]
            break
        if start > 0:
            _LOGGER.debug("Resynchronising: dropping %d leading bytes", start)
            del buffer[:start]
        if len(buffer) < 3:
            break
        declared = buffer[2]
        total_len = declared + 3
        if len(buffer) < total_len:
            break
        frames.append(bytes(buffer[:total_len]))
        del buffer[:total_len]
    return frames, buffer


def _parse_frame(frame: bytes) -> dict[str, Any]:
    """Parse a single complete frame. Raises ProtocolError on any mismatch."""
    if len(frame) < 4 or not frame.startswith(PREFIX):
        raise ProtocolError(f"Malformed frame: {frame.hex()}")
    declared = frame[2]
    expected = declared + 3
    if len(frame) < expected:
        raise ProtocolError(f"Truncated frame: need {expected}, got {len(frame)}")
    body = frame[2 : 2 + declared]
    checksum = frame[2 + declared]
    calculated = calculate_checksum(body)
    if checksum != calculated:
        raise ProtocolError(
            "Checksum mismatch: got 0x%02x, expected 0x%02x (%s)",
            checksum, calculated, frame.hex(),
        )
    return {
        "length": declared,
        "payload": bytes(body[1:]),
        "checksum": checksum,
        "raw": frame,
    }


class HaierProtocol:
    """Stateful Haier protocol codec: buffer + parser + packet factory."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    # ----- decoding -----
    def parse_response(self, data: bytes) -> list[dict[str, Any]]:
        """Feed raw bytes into the buffer and return every fully parsed frame."""
        if data:
            self._buffer.extend(data)
        frames, self._buffer = extract_frames(self._buffer)
        parsed: list[dict[str, Any]] = []
        for frame in frames:
            try:
                parsed.append(_parse_frame(frame))
            except ProtocolError as exc:
                _LOGGER.warning("Skipping malformed frame %s: %s", frame.hex(), exc)
        return parsed

    # ----- encoding -----
    @staticmethod
    def _finalize(body: bytes) -> bytes:
        checksum = calculate_checksum(body)
        return PREFIX + body + bytes([checksum])

    def create_get_status_packet(self) -> bytes:
        """Query current status (frame length 0x07 as in the TS library)."""
        body = bytes([0x07, CMD_STATUS, SET_FLAGS_QUERY, 0x00, 0x00, 0x00])
        return self._finalize(body)

    def create_set_state_packet(
        self,
        power: bool,
        mode: int | None = None,
        temperature: float | None = None,
        fan_speed: int | None = None,
    ) -> bytes:
        """Build a set-state control packet.

        Layout matches the TS library: control code 0x6D followed by the
        control flags and state bytes. Bytes not provided keep current
        values on the device side (0x00 placeholders).
        """
        data = bytearray()
        data.append(CMD_CONTROL)
        data.append(SET_FLAGS_CONTROL)
        data.append(0x01 if power else 0x00)
        data.append(mode if mode is not None else 0x00)

        if temperature is not None:
            clamped = max(MIN_TEMP, min(MAX_TEMP, temperature))
            temp_byte = int((clamped - MIN_TEMP) * 2) & 0xFF
        else:
            temp_byte = 0x00
        data.append(temp_byte)
        data.append(fan_speed if fan_speed is not None else 0x00)

        # Pad to a fixed 15-byte state payload (as used by the original library).
        while len(data) < 15:
            data.append(0x00)

        length = len(data) + 1  # data + checksum byte
        body = bytes([length]) + bytes(data)
        return self._finalize(body)