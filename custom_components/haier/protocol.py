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

@dataclass
class State:
    """Device state structure."""
    current_temperature: int = 21
    target_temperature: int = 21
    fan_speed: int = 0  # 0=auto, 1=low, 2=medium, 3=high
    mode: int = 0       # 0=auto, 1=cool, 2=heat, 3=dry, 4=fan
    health: bool = False
    limits: int = 0     # 0=off, 1=vertical only
    power: bool = False

class HaierProtocol:
    """Protocol handler for Haier AC communication using official protocol."""
    
    def __init__(self, mac_address: str):
        """Initialize protocol handler."""
        # MAC address should be 12 hex chars
        self.mac = mac_address.upper().replace(':', '').replace('-', '')
        if len(self.mac) != 12:
            raise ValueError(f"Invalid MAC address length: {mac_address}")
        
        # Protocol constants from TS library
        self.REQUEST_HEADER = bytes.fromhex('00 00 27 14 00 00 00 00')
        self.RESPONSE_HEADER = bytes.fromhex('00 00 27 15 00 00 00 00')
        
    def _zero16(self) -> bytes:
        """Return 16 zero bytes."""
        return bytes(16)
    
    def _mac_address_bytes(self) -> bytes:
        """Convert MAC address to bytes as in TS library."""
        # In TS library: MAC as ASCII chars + 4 zero bytes
        mac_ascii = self.mac.encode('ascii')
        mac_with_padding = mac_ascii + b'\x00\x00\x00\x00'
        return mac_with_padding
    
    def _order_byte(self, seq: int) -> bytes:
        """Return order byte as in TS library (4 bytes, last byte is seq)."""
        return bytes([0x00, 0x00, 0x00, seq % 256])
    
    def _len4(self, cmd: bytes) -> bytes:
        """Return length of command as 4 bytes (last byte is length)."""
        length = len(cmd)
        return bytes([0x00, 0x00, 0x00, length])
    
    def _append_checksum(self, hex_str: str) -> str:
        """Append checksum as in TS library."""
        # Remove non-hex chars
        hex_clean = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
        
        # Calculate checksum like in TS library
        total = 0
        for i, c in enumerate(hex_clean):
            digit = int(c, 16)
            if i % 2 == 0:
                total += digit * 16
            else:
                total += digit
        
        checksum = (total - 2 * 255) & 0xFF
        checksum_hex = format(checksum, '02x')
        
        return f"{hex_str} {checksum_hex}"
    
    def _command_hello(self) -> bytes:
        """Create hello command bytes."""
        return bytes.fromhex('ff ff 0a 00 00 00 00 00 00 01 4d 01 59')
    
    def _command_init(self) -> bytes:
        """Create init command bytes."""
        return bytes.fromhex('ff ff 08 00 00 00 00 00 00 73 7b')
    
    def _command_on(self) -> bytes:
        """Create on command bytes."""
        return bytes.fromhex('ff ff 0a 00 00 00 00 00 00 01 4d 02 5a')
    
    def _command_off(self) -> bytes:
        """Create off command bytes."""
        return bytes.fromhex('ff ff 0a 00 00 00 00 00 00 01 4d 03 5b')
    
    def _command_set_state(self, state: State) -> bytes:
        """Create set state command bytes."""
        # Build hex string like in TS library
        hex_str = 'ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00'
        
        # Add mode
        hex_str += f' 00 0{state.mode}'
        
        # Add fan speed
        hex_str += f' 00 0{state.fan_speed}'
        
        # Add limits
        hex_str += f' 00 0{state.limits}'
        
        # Add power (special encoding as in TS: 9 if health else 1)
        power_byte = 9 if state.health else 1
        hex_str += f' 00 0{power_byte}'
        
        # Add health
        health_byte = 1 if state.health else 0
        hex_str += f' 00 0{health_byte}'
        
        # Add zeros
        hex_str += ' 00 00'
        
        # Add target temperature (offset by 16)
        temp_offset = state.target_temperature - 16
        hex_str += f' 00 0{temp_offset:x}'
        
        # Append checksum
        hex_str_with_checksum = self._append_checksum(hex_str)
        
        # Convert to bytes
        return bytes.fromhex(hex_str_with_checksum.replace(' ', ''))
    
    def _build_packet(self, seq: int, command: bytes) -> bytes:
        """Build complete packet as in TS library."""
        parts = [
            self.REQUEST_HEADER,
            self._zero16(),
            self._zero16(),
            self._mac_address_bytes(),
            self._zero16(),
            self._order_byte(seq),
            self._len4(command),
            command,
        ]
        
        return b''.join(parts)
    
    def create_hello_packet(self, seq: int = 0) -> bytes:
        """Create hello packet."""
        command = self._command_hello()
        return self._build_packet(seq, command)
    
    def create_init_packet(self, seq: int = 0) -> bytes:
        """Create initialization packet."""
        command = self._command_init()
        return self._build_packet(seq, command)
    
    def create_on_packet(self, seq: int = 1) -> bytes:
        """Create packet to turn device on."""
        command = self._command_on()
        return self._build_packet(seq, command)
    
    def create_off_packet(self, seq: int = 1) -> bytes:
        """Create packet to turn device off."""
        command = self._command_off()
        return self._build_packet(seq, command)
    
    def create_set_state_packet(self, state: State, seq: int = 1) -> bytes:
        """Create packet to set device state."""
        command = self._command_set_state(state)
        return self._build_packet(seq, command)
    
    def create_status_request_packet(self, seq: int = 10) -> bytes:
        """Create status request packet."""
        # In TS library, status request is done via setState with current state
        # But we can use a simple command similar to hello
        command = bytes.fromhex('ff ff 01 00 00 00 00 00 00 01 4d 00 4c')
        return self._build_packet(seq, command)
    
    def parse_response(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse response frames from device."""
        frames = []
        i = 0
        
        _LOGGER.debug(f"Parsing response data ({len(data)} bytes): {data.hex()}")
        
        # Parse like TS library's TheParser
        while i < len(data):
            try:
                # Look for response header
                if i + 8 <= len(data) and data[i:i+8] == self.RESPONSE_HEADER:
                    frame = self._parse_frame(data[i:])
                    if frame:
                        frames.append(frame)
                        i += frame.get('frame_length', 8)
                    else:
                        i += 1
                else:
                    i += 1
            except Exception as e:
                _LOGGER.debug(f"Error parsing at index {i}: {e}")
                i += 1
        
        return frames
    
    def _parse_frame(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse a single response frame."""
        if len(data) < 8:
            return None
        
        # Check header
        if data[0:8] != self.RESPONSE_HEADER:
            return None
        
        # Skip 4 zero bytes (res_start_zero4)
        if len(data) < 12:
            return None
        
        # Parse like TS parser states
        state = 'start'
        result = {}
        i = 8  # Start after header
        
        # Parse through the structure
        try:
            # Skip first 16 zero bytes (first_zero)
            if len(data) < i + 16:
                return None
            i += 16
            
            # Skip second 16 zero bytes (second_zero)
            if len(data) < i + 16:
                return None
            i += 16
            
            # Parse MAC address (16 bytes, but only first 12 are MAC as ASCII)
            if len(data) < i + 16:
                return None
            
            mac_bytes = data[i:i+12]
            try:
                result['mac'] = mac_bytes.decode('ascii')
            except:
                result['mac'] = mac_bytes.hex()
            
            i += 16
            
            # Skip third 16 zero bytes (third_zero)
            if len(data) < i + 16:
                return None
            i += 16
            
            # Now at scan_command_length state
            # Next 7 bytes, 4th byte (offset=3) is seq
            if len(data) < i + 7:
                return None
            
            result['seq'] = data[i + 3]
            command_length = data[i + 7]
            i += 8  # Move to command start
            
            # Parse command
            if len(data) < i + command_length:
                return None
            
            command = data[i:i+command_length]
            result['command'] = command
            
            # Parse command type (2 bytes after 0xff 0xff)
            if command_length >= 3 and command[0] == 0xff and command[1] == 0xff:
                result['command_type'] = command[2]
                
                # Parse state if it's a state response (0x22)
                if command[2] == 0x22 and command_length >= 34:
                    state_data = self._parse_state_data(command)
                    result['data'] = state_data
            
            result['frame_length'] = i + command_length - 8  # Starting from header
            
            return result
            
        except Exception as e:
            _LOGGER.debug(f"Error parsing frame: {e}")
            return None
    
    def _parse_state_data(self, command: bytes) -> Dict[str, Any]:
        """Parse state data from command (type 0x22)."""
        result = {}
        
        try:
            # Parse using structure similar to TS library's stateParser
            # Offset in command: after 0xff 0xff 0x22 and some zeros
            
            # In TS library, state starts at byte 22 of command
            # Structure: 0xffff + mode + fan_speed + limits + power + health + target_temp
            
            # Find the 0xffff marker
            for i in range(len(command) - 1):
                if command[i] == 0xff and command[i+1] == 0xff:
                    start_idx = i + 2
                    if start_idx + 20 <= len(command):
                        # Parse similar to TS stateParser
                        # Skip 8 bytes
                        state_start = start_idx + 8
                        
                        # Current temperature (byte 6 after 0xffff)
                        result['current_temperature'] = command[state_start + 6]
                        
                        # Mode (byte 14 after 0xffff)
                        result['mode'] = command[state_start + 14]
                        
                        # Fan speed (byte 16 after 0xffff)
                        result['fan_speed'] = command[state_start + 16]
                        
                        # Limits (byte 18 after 0xffff)
                        result['limits'] = command[state_start + 18]
                        
                        # Power (byte 20 after 0xffff)
                        result['power'] = command[state_start + 20]
                        
                        # Health (byte 22 after 0xffff)
                        result['health'] = command[state_start + 22]
                        
                        # Target temperature (byte 26 after 0xffff)
                        # In TS: targetTemperature + 16
                        result['target_temperature_raw'] = command[state_start + 26]
                        
                        break
        except Exception as e:
            _LOGGER.debug(f"Error parsing state data: {e}")
        
        return result
    
    def parse_state_response(self, response: Dict[str, Any]) -> Optional[State]:
        """Convert parsed response to State object."""
        if 'data' not in response:
            return None
        
        data = response['data']
        
        try:
            state = State()
            
            # Convert temperatures (like in TS library)
            if 'current_temperature' in data:
                state.current_temperature = data['current_temperature']
            
            if 'target_temperature_raw' in data:
                state.target_temperature = data['target_temperature_raw'] + 16
            
            if 'fan_speed' in data:
                state.fan_speed = data['fan_speed']
            
            if 'mode' in data:
                state.mode = data['mode']
            
            if 'health' in data:
                # Convert like in TS: Boolean(health % 2)
                state.health = bool(data['health'] % 2)
            
            if 'limits' in data:
                state.limits = data['limits']
            
            if 'power' in data:
                # Convert like in TS: Boolean(power % 2)
                state.power = bool(data['power'] % 2)
            
            return state
            
        except Exception as e:
            _LOGGER.debug(f"Error converting to State: {e}")
            return None