"""Protocol implementation for Haier AC based on official protocol specification."""
import struct
import logging
import crcmod
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

class Mode(IntEnum):
    AUTO = 0
    COOL = 1
    HEAT = 2
    DRY = 3
    FAN = 4

class FanSpeed(IntEnum):
    AUTO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

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
    
    def _build_frame(self, frame_type: int, data: bytes = b'', with_crc: bool = False) -> bytes:
        """Build a frame according to actual Haier protocol."""
        # Based on packet analysis: 
        # [separator][length][flags][4-byte reserved][command][data][checksum]
        # command seems to be always 0x01 in responses, but we need to verify for outgoing
        
        flags = FRAME_FLAG_WITH_CRC if with_crc else FRAME_FLAG_NO_CRC
        reserved = b'\x00' * 4  # 4 bytes, not 5!
        
        # For outgoing frames, command is probably 0x01 (based on incoming frames)
        command = 0x01
        
        # Build frame without separator, length, and checksum
        # Structure: flags + reserved + command + frame_type + data
        frame_without_extras = bytes([flags]) + reserved + bytes([command]) + bytes([frame_type]) + data
        
        # Calculate length (includes: flags(1) + reserved(4) + command(1) + frame_type(1) + data(n) + checksum(1))
        length = len(frame_without_extras) + 1  # +1 for checksum
        
        # Calculate checksum (sum of frame_without_extras)
        checksum = sum(frame_without_extras) & 0xFF
        
        # Build final frame
        frame = FRAME_SEPARATOR + bytes([length]) + frame_without_extras + bytes([checksum])
        
        _LOGGER.debug(f"Built frame: length={length}, command=0x{command:02x}, type=0x{frame_type:02x}, checksum=0x{checksum:02x}")
        _LOGGER.debug(f"Frame bytes: {frame.hex()}")
        
        return frame
    
    def create_hello_packet(self) -> bytes:
        """Create hello packet to initiate communication."""
        hello_data = bytes([
            0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x4D, 0x01, 0x59
        ])
        return self._build_frame(CMD_TYPE_HELLO, hello_data, with_crc=False)
    
    def create_init_packet(self) -> bytes:
        """Create initialization packet."""
        init_data = bytes([
            0x00, 0x00, 0x00, 0x00, 0x00, 0x73, 0x7B
        ])
        return self._build_frame(CMD_TYPE_INIT, init_data, with_crc=False)
    
    def create_status_request_packet(self) -> bytes:
        """Create status request packet."""
        # Simple status request - may need MAC address in data
        mac_bytes = bytes.fromhex(self.mac)
        status_data = mac_bytes + b'\x00\x00\x00\x00'  # MAC + padding
        return self._build_frame(CMD_TYPE_STATUS_REQUEST, status_data, with_crc=False)
    
    def create_control_packet(self, state: State) -> bytes:
        """Create control packet to change device state."""
        # Build control data based on state
        control_data = bytearray()
        
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
        
        return self._build_frame(CMD_TYPE_CONTROL, bytes(control_data), with_crc=False)
    
    def create_ack_packet(self) -> bytes:
        """Create ACK packet to acknowledge received frames."""
        # ACK packet data might be empty or contain status
        ack_data = bytes([0x00])  # Simple ACK
        return self._build_frame(CMD_TYPE_ACK, ack_data, with_crc=False)
    
    def parse_response(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse response frames from device."""
        frames = []
        i = 0
        
        _LOGGER.debug(f"Parsing response data ({len(data)} bytes): {data.hex()}")
        
        while i < len(data):
            # Look for frame separator
            if i + 2 <= len(data) and data[i:i+2] == FRAME_SEPARATOR:
                # Try to parse this frame
                frame = self._parse_frame(data[i:])
                if frame:
                    frames.append(frame)
                    i += frame.get('frame_length', 2)
                    _LOGGER.debug(f"Successfully parsed frame, moving index to {i}")
                else:
                    i += 1
            else:
                i += 1
        
        _LOGGER.debug(f"Total frames parsed: {len(frames)}")
        return frames
    
    def _parse_frame(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse a single frame starting at the beginning of data."""
        if len(data) < 10:
            _LOGGER.debug(f"Data too short: {len(data)} bytes")
            return None
        
        # Check separator
        if data[0:2] != FRAME_SEPARATOR:
            _LOGGER.debug(f"Invalid separator: {data[0:2].hex()}")
            return None
        
        # Get length
        length = data[2]
        _LOGGER.debug(f"Frame length byte: {length} (0x{length:02x})")
        
        total_frame_size = length + 2
        if len(data) < total_frame_size:
            _LOGGER.debug(f"Not enough data: have {len(data)}, need {total_frame_size}")
            return None
        
        frame_bytes = data[0:total_frame_size]
        
        # For debugging, continue parsing even if checksum is wrong
        _LOGGER.debug(f"DEBUG: Parsing frame (temporarily skipping checksum verification)")
        
        # Parse frame anyway to see what data we get
        frame_data = frame_bytes[2:]  # Skip separator
        
        flags = frame_data[1]
        reserved_bytes_count = 4
        reserved_start = 2
        reserved_end = reserved_start + reserved_bytes_count
        
        if len(frame_data) < reserved_end:
            return None
        
        reserved = frame_data[reserved_start:reserved_end]
        # The byte after reserved is command (always 0x01 in incoming frames)
        command = frame_data[reserved_end]
        
        data_start = reserved_end + 1
        checksum_pos = length - 1
        
        if checksum_pos < data_start:
            return None
        
        checksum = frame_data[checksum_pos]
        # The actual frame data starts from data_start, but the first byte of that data is the real frame type
        frame_data_bytes = frame_data[data_start:checksum_pos] if data_start < checksum_pos else b''
        
        if len(frame_data_bytes) == 0:
            _LOGGER.debug("No frame data bytes")
            return None
        
        # The first byte of frame_data_bytes is the actual frame type
        frame_type = frame_data_bytes[0]
        actual_data = frame_data_bytes[1:]  # The rest is the actual data
        
        # DEBUG: Try different checksum algorithms
        bytes_without_checksum = frame_data[1:checksum_pos]  # From flags to before checksum
        simple_sum = sum(bytes_without_checksum) & 0xFF
        xor_sum = 0
        for b in bytes_without_checksum:
            xor_sum ^= b
        
        # Also try including the length byte
        bytes_with_length = frame_data[0:checksum_pos]  # From length to before checksum
        sum_with_length = sum(bytes_with_length) & 0xFF
        
        _LOGGER.debug(f"DEBUG: Checksum analysis:")
        _LOGGER.debug(f"  Expected: 0x{checksum:02x} ({checksum})")
        _LOGGER.debug(f"  Simple sum (without length): 0x{simple_sum:02x} ({simple_sum})")
        _LOGGER.debug(f"  XOR sum (without length): 0x{xor_sum:02x} ({xor_sum})")
        _LOGGER.debug(f"  Sum with length: 0x{sum_with_length:02x} ({sum_with_length})")
        _LOGGER.debug(f"  Bytes for check ({len(bytes_without_checksum)}): {bytes_without_checksum.hex()}")
        
        # Parse frame data (skip checksum verification for now)
        parsed_data = self._parse_frame_data(frame_type, actual_data)
        
        return {
            'frame_length': total_frame_size,
            'flags': flags,
            'command': command,  # The byte after reserved (0x01 for all packets?)
            'type': frame_type,  # Actual frame type from data (0x04, 0x06, etc.)
            'data': parsed_data,
            'raw_data': actual_data,
            'checksum_ok': False,  # Temporarily set to False
            'checksum_expected': checksum,
            'checksum_calculated': simple_sum,
        }
    
    def _parse_frame_data(self, frame_type: int, data: bytes) -> Dict[str, Any]:
        """Parse frame data based on frame type."""
        result = {}
        
        _LOGGER.debug(f"Parsing frame data: type=0x{frame_type:02x}, data={data.hex()}")
        
        if frame_type == 0x04:  # ACK frame
            if len(data) >= 1:
                result['ack'] = True
                result['ack_data'] = data.hex()
                # Sometimes ACK may contain status
                if len(data) >= 2:
                    result['ack_status'] = data[1]
        
        elif frame_type == 0x06:  # Response frame with device state
            # Parse response frame with device data
            if len(data) >= 8:
                try:
                    # data: 6d01001d0013007f...
                    # Byte 0: 0x6d = 109 (unknown)
                    # Byte 1: 0x01 = 1 (power? mode?)
                    # Byte 2: 0x00 = 0
                    # Byte 3: 0x1d = 29 (target temperature? 16+13=29?)
                    # Byte 4: 0x00 = 0
                    # Byte 5: 0x13 = 19 (current temperature? 16+3=19?)
                    # Byte 6: 0x00 = 0
                    # Byte 7: 0x7f = 127 (fan speed? 0x7f might mean auto)
                    
                    result['raw_byte0'] = data[0]
                    result['power_or_mode'] = data[1]
                    result['target_temp_raw'] = data[3]
                    result['current_temp_raw'] = data[5]
                    result['fan_speed_raw'] = data[7]
                    
                    # Try to convert to actual values
                    result['target_temperature'] = data[3] + 16 if data[3] <= 15 else 25
                    result['current_temperature'] = data[5] + 16 if data[5] <= 15 else 25
                    
                    # Power state: bit 0 of byte 1
                    result['power'] = bool(data[1] & 0x01)
                    
                    # Mode: bits 1-3 of byte 1
                    mode_bits = (data[1] >> 1) & 0x07
                    result['mode'] = mode_bits
                    
                    # Fan speed: byte 7
                    fan_speed_map = {0x00: 0, 0x01: 1, 0x02: 2, 0x03: 3, 0x7f: 0}
                    result['fan_speed'] = fan_speed_map.get(data[7], 0)
                    
                    _LOGGER.debug(f"Parsed state: power={result.get('power')}, mode={result.get('mode')}, "
                                 f"target_temp={result.get('target_temperature')}, "
                                 f"current_temp={result.get('current_temperature')}, "
                                 f"fan_speed={result.get('fan_speed')}")
                    
                except (IndexError, ValueError) as e:
                    _LOGGER.debug(f"Error parsing state frame: {e}")
        else:
            result['unknown_type'] = frame_type
            result['data'] = data.hex()
        
        return result
    
    def create_on_packet(self) -> bytes:
        """Create packet to turn device on."""
        state = State(power=True)
        return self.create_control_packet(state)
    
    def create_off_packet(self) -> bytes:
        """Create packet to turn device off."""
        state = State(power=False)
        return self.create_control_packet(state)
    
    def create_set_state_packet(self, state: State) -> bytes:
        """Create packet to set device state."""
        return self.create_control_packet(state)
    
    def create_ack_response_packet(self, ack_data: bytes = b'\x5a\x00') -> bytes:
        """Create ACK response packet to acknowledge device messages."""
        # ACK-пакет типа 0x04 с данными 0x5a00 (возможно, это код подтверждения)
        return self._build_frame(0x04, ack_data, with_crc=False)