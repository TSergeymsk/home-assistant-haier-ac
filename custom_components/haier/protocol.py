"""Protocol implementation for Haier AC based on official protocol specification."""
import struct
import logging
import crcmod
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

# Добавленные enum - которые отсутствовали
class Mode(IntEnum):
    AUTO = 0
    COOL = 1
    HEAT = 2
    DRY = 3
    FAN = 4

class FanSpeed(IntEnum):
    AUTO = 0
    MIN = 1    # Было LOW
    MID = 2    # Было MEDIUM
    MAX = 3    # Было HIGH

class Limits(IntEnum):
    OFF = 0
    ONLY_VERTICAL = 1

# Protocol constants from official documentation
FRAME_SEPARATOR = b'\xFF\xFF'
FRAME_FLAG_WITH_CRC = 0x40
FRAME_FLAG_NO_CRC = 0x00

# Protocol types (need to be determined experimentally)
PROTOCOL_TYPE_SMARTAIR2 = 0x01  # For older units
PROTOCOL_TYPE_HON = 0x02        # For newer units with hOn app

# Command types based on observed behavior
CMD_TYPE_STATUS_REQUEST = 0x01
CMD_TYPE_STATUS_RESPONSE = 0x02
CMD_TYPE_CONTROL = 0x03
CMD_TYPE_ACK = 0x04
CMD_TYPE_HELLO = 0x0A
CMD_TYPE_INIT = 0x08

@dataclass
class State:
    """Device state structure."""
    current_temperature: int = 21
    target_temperature: int = 21
    fan_speed: int = 0  # 0=auto, 1=low, 2=medium, 3=high
    mode: int = 0       # 0=fan, 1=cool, 2=heat, 3=auto, 4=dry
    health: bool = False
    limits: int = 0     # 0=off, 1=vertical only
    power: bool = False
    display: bool = True
    beep: bool = True

class HaierProtocol:
    """Protocol handler for Haier AC communication using official protocol."""
    
    def __init__(self, mac_address: str, protocol_type: int = PROTOCOL_TYPE_SMARTAIR2):
        """Initialize protocol handler."""
        # MAC address should be 12 hex chars
        self.mac = mac_address.upper().replace(':', '').replace('-', '')
        if len(self.mac) != 12:
            raise ValueError(f"Invalid MAC address length: {mac_address}")
        
        self.protocol_type = protocol_type
        self.seq = 0
        self.crc16_func = crcmod.predefined.mkPredefinedCrcFun('crc-16')
        
    def _get_next_seq(self) -> int:
        """Get next sequence number."""
        seq = self.seq
        self.seq = (self.seq + 1) % 256
        return seq
    
    def _build_frame(self, frame_type: int, data: bytes = b'', with_crc: bool = True) -> bytes:
        """Build a frame according to Haier protocol structure [citation:5]."""
        # Frame structure:
        # - Separator: 2 bytes (0xFF 0xFF)
        # - Length: 1 byte (total frame length)
        # - Flags: 1 byte (0x40 = with CRC, 0x00 = without)
        # - Reserved: 5 bytes (0x00)
        # - Type: 1 byte
        # - Data: n bytes
        # - Checksum: 1 byte (sum of bytes except separator and checksum itself)
        # - CRC: 2 bytes (only if flags indicate)
        
        # Build frame without separator, checksum and CRC
        flags = FRAME_FLAG_WITH_CRC if with_crc else FRAME_FLAG_NO_CRC
        reserved = b'\x00' * 5
        
        frame_without_extras = bytes([
            flags
        ]) + reserved + bytes([frame_type]) + data
        
        # Calculate length (includes flags, reserved, type, data, checksum, and CRC if present)
        length = len(frame_without_extras) + 1  # +1 for checksum
        if with_crc:
            length += 2  # +2 for CRC
        
        # Calculate checksum (sum of all bytes except separator and checksum itself)
        # This includes length byte too
        frame_for_checksum = bytes([length]) + frame_without_extras
        checksum = sum(frame_for_checksum) & 0xFF
        
        # Build final frame
        frame = FRAME_SEPARATOR + bytes([length]) + frame_without_extras + bytes([checksum])
        
        # Add CRC if needed
        if with_crc:
            # CRC is calculated on everything except separator, checksum and CRC itself
            crc_data = frame[2:-1]  # Skip separator and checksum
            crc = self.crc16_func(crc_data)
            frame += struct.pack('<H', crc)  # Little endian
        
        return frame
    
    def create_hello_packet(self) -> bytes:
        """Create hello packet to initiate communication."""
        # Based on observed data: hello command is 0x0A with specific data
        # Data from original: 0x00 0x00 0x00 0x00 0x00 0x01 0x4D 0x01 0x59
        hello_data = bytes([
            0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x4D, 0x01, 0x59
        ])
        return self._build_frame(CMD_TYPE_HELLO, hello_data)
    
    def create_init_packet(self) -> bytes:
        """Create initialization packet."""
        # Based on observed data: init command is 0x08 with specific data
        # Data from original: 0x00 0x00 0x00 0x00 0x00 0x73 0x7B
        init_data = bytes([
            0x00, 0x00, 0x00, 0x00, 0x00, 0x73, 0x7B
        ])
        return self._build_frame(CMD_TYPE_INIT, init_data)
    
    def create_status_request_packet(self) -> bytes:
        """Create status request packet."""
        # Simple status request - may need MAC address in data
        mac_bytes = bytes.fromhex(self.mac)
        status_data = mac_bytes + b'\x00\x00\x00\x00'  # MAC + padding
        return self._build_frame(CMD_TYPE_STATUS_REQUEST, status_data)
    
    def create_control_packet(self, state: State) -> bytes:
        """Create control packet to change device state."""
        # Build control data based on state
        # This needs to be determined experimentally
        control_data = bytearray()
        
        # Start with some header
        control_data.extend([0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x4D, 0x5F])
        control_data.extend([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        control_data.extend([0x00, 0x00])  # More zeros
        
        # Add mode
        control_data.extend([0x00, state.mode])
        
        # Add fan speed
        control_data.extend([0x00, state.fan_speed])
        
        # Add swing mode
        control_data.extend([0x00, state.limits])
        
        # Add power (special encoding)
        power_byte = 0x09 if state.power else 0x01
        control_data.extend([0x00, power_byte])
        
        # Add health mode
        health_byte = 0x01 if state.health else 0x00
        control_data.extend([0x00, health_byte])
        
        # Add zeros
        control_data.extend([0x00, 0x00])
        
        # Add target temperature (offset by 16)
        temp_offset = max(0, min(15, state.target_temperature - 16))
        control_data.extend([0x00, temp_offset])
        
        return self._build_frame(CMD_TYPE_CONTROL, bytes(control_data))
    
    def parse_response(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse response frames from device."""
        frames = []
        i = 0
        
        while i < len(data):
            # Look for frame separator
            if i + 2 <= len(data) and data[i:i+2] == FRAME_SEPARATOR:
                # Try to parse this frame
                frame = self._parse_frame(data[i:])
                if frame:
                    frames.append(frame)
                    i += frame.get('frame_length', 2)
                else:
                    i += 1
            else:
                i += 1
        
        return frames
    
    def _parse_frame(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse a single frame starting at the beginning of data."""
        _LOGGER.debug(f"Full raw data chunk ({len(data)} bytes): {data.hex()}")
        if len(data) < 12:  # Minimum frame size
            return None
        
        # Check separator
        if data[0:2] != FRAME_SEPARATOR:
            return None
        
        # Get length
        length = data[2]
        
        # Check if we have enough data
        if len(data) < length + 2:  # +2 for separator
            return None
        
        # Extract frame data (without separator)
        frame_data = data[2:2+length]
        
        # Parse frame components
        flags = frame_data[1]
        reserved = frame_data[2:7]
        frame_type = frame_data[7]
        
        # Data starts at position 8
        data_start = 8
        checksum_pos = length - 1
        if flags & FRAME_FLAG_WITH_CRC:
            checksum_pos -= 2  # Account for CRC
        
        frame_data_bytes = frame_data[data_start:checksum_pos]
        checksum = frame_data[checksum_pos]
        
        # Verify checksum
        calculated_checksum = sum(frame_data[:checksum_pos]) & 0xFF
        if calculated_checksum != checksum:
            _LOGGER.debug(f"Checksum mismatch: {calculated_checksum} != {checksum}")
            return None
        
        # Parse frame data based on type
        parsed_data = self._parse_frame_data(frame_type, frame_data_bytes)
        
        return {
            'frame_length': length + 2,
            'flags': flags,
            'type': frame_type,
            'data': parsed_data,
            'raw_data': frame_data_bytes
        }
    
    def _parse_frame_data(self, frame_type: int, data: bytes) -> Dict[str, Any]:
        """Parse frame data based on frame type."""
        result = {}
        
        if frame_type == CMD_TYPE_STATUS_RESPONSE:
            # Parse status response
            if len(data) >= 44:
                try:
                    # Parse temperatures (might be in different positions)
                    result['current_temperature'] = data[12] if len(data) > 12 else 21
                    result['target_temperature'] = (data[42] + 16) if len(data) > 42 else 21
                    
                    # Parse mode and fan
                    if len(data) > 30:
                        result['mode'] = data[30]
                    if len(data) > 32:
                        result['fan_speed'] = data[32]
                    
                    # Parse flags
                    if len(data) > 34:
                        result['limits'] = data[34]
                    if len(data) > 36:
                        result['power'] = bool(data[36] & 0x01)
                    if len(data) > 38:
                        result['health'] = bool(data[38] & 0x01)
                        
                except (IndexError, ValueError) as e:
                    _LOGGER.debug(f"Error parsing status: {e}")
        
        elif frame_type == CMD_TYPE_ACK:
            # Acknowledgement frame
            result['acknowledged'] = True
            if data:
                result['seq'] = data[0] if len(data) > 0 else 0
        
        return result