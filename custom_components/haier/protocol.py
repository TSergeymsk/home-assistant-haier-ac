"""Haier protocol implementation."""
import struct
from enum import IntEnum
from typing import Optional
import logging

_LOGGER = logging.getLogger(__name__)


class Mode(IntEnum):
    AUTO = 0
    COOL = 1
    DRY = 2
    HEAT = 3
    FAN = 4


class FanSpeed(IntEnum):
    AUTO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Limits(IntEnum):
    OFF = 0x00
    VERTICAL = 0x01
    HORIZONTAL = 0x02
    BOTH = 0x03
    NONE = 0x00


class State:
    def __init__(self, mode=Mode.AUTO, fan_speed=FanSpeed.AUTO,
                 limits=Limits.NONE, health=False, target_temperature=24):
        self.mode = mode
        self.fan_speed = fan_speed
        self.limits = limits
        self.health = health
        self.target_temperature = target_temperature

    def __repr__(self):
        return (f"State(mode={self.mode}, fan_speed={self.fan_speed}, "
                f"limits={self.limits}, health={self.health}, "
                f"target_temperature={self.target_temperature})")


class HaierProtocol:
    def __init__(self, mac: str, device_type: int = 0x22):
        self.mac = mac
        self._mac = mac.replace(":", "").lower()
        self._device_type = device_type
        self._seq = 0

    def _mac_address_bytes(self) -> bytes:
        return bytes.fromhex(self._mac)[::-1]

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) % 256
        return self._seq

    def _build_packet(self, command: bytes, seq: int) -> bytes:
        header = bytes.fromhex("00 00 27 14 00 00 00 00")
        zeros1 = bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = struct.pack(">I", seq)
        cmd_len_bytes = struct.pack(">I", len(command))
        return header + zeros1 + mac_bytes + zeros2 + seq_bytes + cmd_len_bytes + command

    def create_get_state_packet(self) -> bytes:
        seq = self._next_seq()
        hex_str = ("ff ff 22 00 00 00 00 00 00 01 4d 5f "
                   "00 00 00 00 00 00 00 00 00 00 "
                   "00 00 00 00 00 00 00 00 00 00 00 00")
        hex_clean = hex_str.replace(" ", "")
        total = 0
        for i, c in enumerate(hex_clean):
            digit = int(c, 16)
            if i % 2 == 0:
                total += digit * 16
            else:
                total += digit
        checksum = (total - 2 * 255) % 256
        hex_str += f" {checksum:02x}"
        command = bytes.fromhex(hex_str.replace(" ", ""))
        return self._build_packet(command, seq)

    def create_set_state_packet(self, state: State) -> bytes:
        seq = self._next_seq()
        hex_str = "ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00"
        hex_str += f" 00 {state.mode:02x}"
        hex_str += f" 00 {state.fan_speed:02x}"
        hex_str += f" 00 {state.limits:02x}"
        power_health = 0x01 | (0x08 if state.health else 0x00)
        hex_str += f" 00 {power_health:02x}"
        hex_str += " 00 00"
        temp_offset = state.target_temperature - 16
        hex_str += f" 00 00 00 {temp_offset:02x}"
        # checksum
        hex_clean = hex_str.replace(" ", "")
        total = 0
        for i, c in enumerate(hex_clean):
            digit = int(c, 16)
            if i % 2 == 0:
                total += digit * 16
            else:
                total += digit
        checksum = (total - 2 * 255) % 256
        hex_str += f" {checksum:02x}"
        command = bytes.fromhex(hex_str.replace(" ", ""))
        return self._build_packet(command, seq)

    def parse_response(self, data: bytes) -> Optional[State]:
        if len(data) < 44:
            _LOGGER.warning("Response too short")
            return None
        if data[0:4] != b'\x00\x00\x27\x14':
            _LOGGER.warning("Invalid response header")
            return None
        offset = 8 + 16 + 6 + 16 + 4 + 4
        if len(data) < offset:
            _LOGGER.warning("Not enough data")
            return None
        cmd = data[offset:]
        if len(cmd) < 42:
            _LOGGER.warning("Command too short")
            return None
        if cmd[0:3] != b'\xff\xff\x22':
            _LOGGER.warning("Invalid command signature")
            return None
        mode = cmd[24] if len(cmd) > 24 else 0
        fan_speed = cmd[26] if len(cmd) > 26 else 0
        limits = cmd[28] if len(cmd) > 28 else 0
        power_health = cmd[30] if len(cmd) > 30 else 0
        health = bool(power_health & 0x08)
        temp_raw = cmd[36] if len(cmd) > 36 else 0
        target_temperature = temp_raw + 16
        return State(mode, fan_speed, limits, health, target_temperature)
