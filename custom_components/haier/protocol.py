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
    """Protocol handler for Haier AC communication."""
    
    def __init__(self, mac_address: str):
        """Initialize protocol handler."""
        # MAC address should be 12 hex chars
        self.mac = mac_address.upper().replace(':', '').replace('-', '')
        if len(self.mac) != 12:
            raise ValueError(f"Invalid MAC address length: {mac_address}")
    
    def create_hello_packet(self, seq: int = 0) -> bytes:
        """Create hello packet."""
        # Based on TS library: hello command with sequence
        header = bytes.fromhex('00 00 27 14 00 00 00 00')
        zeros = bytes(16) + bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = bytes([0x00, 0x00, 0x00, seq % 256])
        cmd_len = bytes([0x00, 0x00, 0x00, 0x13])  # 19 bytes for hello command
        command = bytes.fromhex('ff ff 0a 00 00 00 00 00 00 01 4d 01 59')
        
        return header + zeros + mac_bytes + zeros2 + seq_bytes + cmd_len + command
    
    def create_init_packet(self, seq: int = 0) -> bytes:
        """Create initialization packet."""
        # Based on TS library: init command with sequence
        header = bytes.fromhex('00 00 27 14 00 00 00 00')
        zeros = bytes(16) + bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = bytes([0x00, 0x00, 0x00, seq % 256])
        cmd_len = bytes([0x00, 0x00, 0x00, 0x0d])  # 13 bytes for init command
        command = bytes.fromhex('ff ff 08 00 00 00 00 00 00 73 7b')
        
        return header + zeros + mac_bytes + zeros2 + seq_bytes + cmd_len + command
    
    def _mac_address_bytes(self) -> bytes:
        """Convert MAC address to bytes as in TS library."""
        # MAC as ASCII chars + 4 zero bytes
        mac_ascii = self.mac.encode('ascii')
        mac_with_padding = mac_ascii + b'\x00\x00\x00\x00'
        return mac_with_padding.ljust(16, b'\x00')
    
    def create_status_request_packet(self, seq: int = 10) -> bytes:
        """Create status request packet."""
        # Simple status request - use hello format but different command
        header = bytes.fromhex('00 00 27 14 00 00 00 00')
        zeros = bytes(16) + bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = bytes([0x00, 0x00, 0x00, seq % 256])
        cmd_len = bytes([0x00, 0x00, 0x00, 0x0d])  # 13 bytes for status request
        command = bytes.fromhex('ff ff 01 00 00 00 00 00 00 01 4d 00 4c')
        
        return header + zeros + mac_bytes + zeros2 + seq_bytes + cmd_len + command
    
    def create_on_packet(self, seq: int = 1) -> bytes:
        """Create packet to turn device on."""
        header = bytes.fromhex('00 00 27 14 00 00 00 00')
        zeros = bytes(16) + bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = bytes([0x00, 0x00, 0x00, seq % 256])
        cmd_len = bytes([0x00, 0x00, 0x00, 0x13])  # 19 bytes for on command
        command = bytes.fromhex('ff ff 0a 00 00 00 00 00 00 01 4d 02 5a')
        
        return header + zeros + mac_bytes + zeros2 + seq_bytes + cmd_len + command
    
    def create_off_packet(self, seq: int = 1) -> bytes:
        """Create packet to turn device off."""
        header = bytes.fromhex('00 00 27 14 00 00 00 00')
        zeros = bytes(16) + bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = bytes([0x00, 0x00, 0x00, seq % 256])
        cmd_len = bytes([0x00, 0x00, 0x00, 0x13])  # 19 bytes for off command
        command = bytes.fromhex('ff ff 0a 00 00 00 00 00 00 01 4d 03 5b')
        
        return header + zeros + mac_bytes + zeros2 + seq_bytes + cmd_len + command
    
    def create_set_state_packet(self, state: State, seq: int = 1) -> bytes:
        """Create packet to set device state."""
        # Build command like in TS library
        hex_str = 'ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00'
        hex_str += f' 00 0{state.mode}'
        hex_str += f' 00 0{state.fan_speed}'
        hex_str += f' 00 0{state.limits}'
        power_byte = 9 if state.health else 1
        hex_str += f' 00 0{power_byte}'
        health_byte = 1 if state.health else 0
        hex_str += f' 00 0{health_byte}'
        hex_str += ' 00 00'
        temp_offset = state.target_temperature - 16
        hex_str += f' 00 0{temp_offset:x}'
        
        # Calculate checksum
        hex_clean = hex_str.replace(' ', '')
        total = 0
        for i, c in enumerate(hex_clean):
            digit = int(c, 16)
            if i % 2 == 0:
                total += digit * 16
            else:
                total += digit
        
        checksum = (total - 2 * 255) & 0xFF
        hex_str += f' {checksum:02x}'
        
        command = bytes.fromhex(hex_str.replace(' ', ''))
        command_len = len(command)
        
        header = bytes.fromhex('00 00 27 14 00 00 00 00')
        zeros = bytes(16) + bytes(16)
        mac_bytes = self._mac_address_bytes()
        zeros2 = bytes(16)
        seq_bytes = bytes([0x00, 0x00, 0x00, seq % 256])
        cmd_len_bytes = bytes([0x00, 0x00, 0x00, command_len])
        
        return header + zeros + mac_bytes + zeros2 + seq_bytes + cmd_len_bytes + command
    
    def parse_response(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse response frames from device."""
        frames = []
        i = 0
        
        while i < len(data):
            # Look for response header 00 00 27 15
            if i + 8 <= len(data) and data[i:i+8] == b'\x00\x00\x27\x15\x00\x00\x00\x00':
                frame = self._parse_frame(data[i:])
                if frame:
                    frames.append(frame)
                    i += frame.get('frame_length', len(data) - i)
                else:
                    i += 1
            else:
                i += 1
        
        return frames
    
    def _parse_frame(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse a single response frame."""
        if len(data) < 100:  # Minimum expected frame size
            return None
        
        try:
            # Parse like TS library parser
            pos = 0
            
            # Check header
            if data[pos:pos+8] != b'\x00\x00\x27\x15\x00\x00\x00\x00':
                return None
            pos += 8
            
            # Skip 32 bytes of zeros
            pos += 32
            
            # Parse MAC address (16 bytes, first 12 are MAC ASCII)
            if pos + 16 > len(data):
                return None
            
            mac_bytes = data[pos:pos+12]
            mac = mac_bytes.decode('ascii', errors='ignore')
            pos += 16
            
            # Skip 16 bytes of zeros
            pos += 16
            
            # Get sequence (4 bytes, last byte is seq)
            if pos + 4 > len(data):
                return None
            
            seq = data[pos + 3]
            pos += 4
            
            # Get command length (4 bytes, last byte is length)
            if pos + 4 > len(data):
                return None
            
            cmd_len = data[pos + 3]
            pos += 4
            
            # Get command
            if pos + cmd_len > len(data):
                return None
            
            command = data[pos:pos+cmd_len]
            
            # Parse command type
            cmd_type = None
            if len(command) >= 3 and command[0] == 0xff and command[1] == 0xff:
                cmd_type = command[2]
            
            # Parse state data if it's a state command (0x22)
            state_data = {}
            if cmd_type == 0x22 and len(command) >= 34:
                # Parse state according to TS library structure
                # The state data starts at byte 10 of the command
                if len(command) >= 34:
                    # Parse structure: 0xffff + 8 bytes + data
                    # Current temperature at offset 8 (0-based from start of command)
                    state_data['current_temperature'] = command[8]
                    
                    # Mode at offset 16
                    state_data['mode'] = command[16]
                    
                    # Fan speed at offset 18
                    state_data['fan_speed'] = command[18]
                    
                    # Limits at offset 20
                    state_data['limits'] = command[20]
                    
                    # Power at offset 22 (odd = on, even = off)
                    power_raw = command[22]
                    state_data['power'] = bool(power_raw % 2)
                    
                    # Health at offset 24
                    health_raw = command[24]
                    state_data['health'] = bool(health_raw % 2)
                    
                    # Target temperature at offset 28 (with +16 offset)
                    target_temp_raw = command[28]
                    state_data['target_temperature'] = target_temp_raw + 16
            
            frame_length = pos + cmd_len
            
            return {
                'type': cmd_type,
                'command': cmd_type,  # For compatibility
                'seq': seq,
                'data': state_data,
                'frame_length': frame_length,
                'mac': mac
            }
            
        except Exception as e:
            _LOGGER.debug(f"Error parsing frame: {e}")
            return None