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
        # [separator][length][flags][4-byte reserved][type][data][checksum]
        
        flags = FRAME_FLAG_WITH_CRC if with_crc else FRAME_FLAG_NO_CRC
        reserved = b'\x00' * 4  # 4 bytes, not 5!
        
        # Build frame without separator and checksum
        frame_without_extras = bytes([flags]) + reserved + bytes([frame_type]) + data
        
        # Calculate length (includes: flags(1) + reserved(4) + type(1) + data(n) + checksum(1))
        length = len(frame_without_extras) + 1  # +1 for checksum
        
        # Calculate checksum (sum of frame_without_extras)
        checksum = sum(frame_without_extras) & 0xFF
        
        # Build final frame
        frame = FRAME_SEPARATOR + bytes([length]) + frame_without_extras + bytes([checksum])
        
        _LOGGER.debug(f"Built frame: length={length}, type=0x{frame_type:02x}, checksum=0x{checksum:02x}")
        _LOGGER.debug(f"Frame bytes: {frame.hex()}")
        
        return frame
    
    def create_hello_packet(self) -> bytes:
        """Create hello packet to initiate communication."""
        # Based on observed data: hello command is 0x0A with specific data
        # Data from original: 0x00 0x00 0x00 0x00 0x00 0x01 0x4D 0x01 0x59
        hello_data = bytes([
            0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x4D, 0x01, 0x59
        ])
        return self._build_frame(CMD_TYPE_HELLO, hello_data, with_crc=False)
    
    def create_init_packet(self) -> bytes:
        """Create initialization packet."""
        # Based on observed data: init command is 0x08 with specific data
        # Data from original: 0x00 0x00 0x00 0x00 0x00 0x73 0x7B
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
        
        return self._build_frame(CMD_TYPE_CONTROL, bytes(control_data), with_crc=False)
    
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
        if len(data) < 10:  # Minimum frame size: separator(2) + length(1) + flags(1) + reserved(4) + type(1) + checksum(1)
            _LOGGER.debug(f"Data too short: {len(data)} bytes")
            return None
        
        # Check separator
        if data[0:2] != FRAME_SEPARATOR:
            _LOGGER.debug(f"Invalid separator: {data[0:2].hex()}")
            return None
        
        # Get length (including length byte itself, flags, reserved, type, data, checksum)
        length = data[2]
        _LOGGER.debug(f"Frame length byte: {length} (0x{length:02x})")
        
        # Check if we have enough data (total frame size = length + 2 for separator)
        total_frame_size = length + 2
        if len(data) < total_frame_size:
            _LOGGER.debug(f"Not enough data: have {len(data)}, need {total_frame_size}")
            return None
        
        # Extract the complete frame (including separator)
        frame_bytes = data[0:total_frame_size]
        _LOGGER.debug(f"Full frame ({total_frame_size} bytes): {frame_bytes.hex()}")
        
        # Frame data starts at position 2 (after separator)
        frame_data = frame_bytes[2:]
        
        # Parse components based on ACTUAL packet structure
        # From packets we see: [length][flags][4-byte reserved][frame_type][data...][checksum]
        
        flags = frame_data[1]
        _LOGGER.debug(f"Flags: 0x{flags:02x}")
        
        # IMPORTANT: Based on packet analysis, reserved bytes are 4 bytes
        reserved_bytes_count = 4
        reserved_start = 2
        reserved_end = reserved_start + reserved_bytes_count
        
        if len(frame_data) < reserved_end:
            _LOGGER.debug(f"Frame too short for reserved bytes")
            return None
        
        reserved = frame_data[reserved_start:reserved_end]
        frame_type = frame_data[reserved_end]
        _LOGGER.debug(f"Reserved bytes: {reserved.hex()}, Frame type: 0x{frame_type:02x}")
        
        # Data starts after frame type
        data_start = reserved_end + 1
        
        # Checksum is the last byte before the end
        # Total frame_data length should be 'length'
        if len(frame_data) != length:
            _LOGGER.debug(f"Frame data length mismatch: expected {length}, got {len(frame_data)}")
            # But let's continue anyway for debugging
        
        checksum_pos = length - 1
        if checksum_pos < data_start:
            _LOGGER.debug(f"Invalid checksum position: {checksum_pos} < {data_start}")
            return None
        
        checksum = frame_data[checksum_pos]
        
        # Extract actual data (between data_start and checksum)
        frame_data_bytes = frame_data[data_start:checksum_pos] if data_start < checksum_pos else b''
        
        # Calculate checksum (sum of frame_data bytes EXCLUDING the checksum itself)
        # This should include: flags, reserved, frame_type, and data
        bytes_for_checksum = frame_data[1:checksum_pos]  # From flags to before checksum
        calculated_checksum = sum(bytes_for_checksum) & 0xFF
        
        _LOGGER.debug(f"Checksum: expected=0x{checksum:02x}({checksum}), calculated=0x{calculated_checksum:02x}({calculated_checksum})")
        _LOGGER.debug(f"Bytes for checksum ({len(bytes_for_checksum)}): {bytes_for_checksum.hex()}")
        _LOGGER.debug(f"Frame data bytes ({len(frame_data_bytes)}): {frame_data_bytes.hex()}")
        
        checksum_ok = calculated_checksum == checksum
        if not checksum_ok:
            _LOGGER.debug(f"Checksum mismatch: {calculated_checksum} != {checksum}")
            # For debugging, let's continue anyway
            # return None
        
        # Parse frame data based on type
        parsed_data = self._parse_frame_data(frame_type, frame_data_bytes)
        
        return {
            'frame_length': total_frame_size,
            'flags': flags,
            'type': frame_type,
            'data': parsed_data,
            'raw_data': frame_data_bytes,
            'checksum_ok': checksum_ok
        }
    
    def _parse_frame_data(self, frame_type: int, data: bytes) -> Dict[str, Any]:
        """Parse frame data based on frame type."""
        result = {}
        
        _LOGGER.debug(f"Parsing frame data: type=0x{frame_type:02x}, data={data.hex()}")
        
        if frame_type == 0x04:  # ACK frame from first packet
            # Parse acknowledgement frame
            result['acknowledged'] = True
            if len(data) >= 2:
                result['sub_type'] = data[0]
                result['status'] = data[1]
                _LOGGER.debug(f"ACK frame: sub_type=0x{data[0]:02x}, status=0x{data[1]:02x}")
        
        elif frame_type == 0x06:  # Response frame from second packet
            # Parse response frame with device data
            if len(data) >= 30:
                try:
                    # Based on packet: 6d01001d0013007f0000000000010000000000100000000000085f
                    # This seems to contain device state information
                    
                    # The MAC address appears to be in the first packet, not here
                    # Let's try to extract some state information
                    
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
        
        elif frame_type == 0x01:  # Some other response type
            result['unknown_type_01'] = True
            if len(data) > 0:
                result['data'] = data.hex()
        
        return result
    
    # Add missing methods that are called from device.py
    def create_on_packet(self) -> bytes:
        """Create packet to turn device on."""
        # This needs proper implementation based on protocol
        # For now, create a control packet with power=True
        state = State(power=True)
        return self.create_control_packet(state)
    
    def create_off_packet(self) -> bytes:
        """Create packet to turn device off."""
        # This needs proper implementation based on protocol
        # For now, create a control packet with power=False
        state = State(power=False)
        return self.create_control_packet(state)
    
    def create_set_state_packet(self, state: State) -> bytes:
        """Create packet to set device state."""
        return self.create_control_packet(state)