"""Protocol implementation for Haier AC based on haier-ac-remote library."""
import struct
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

# Constants from haier-ac-remote
class FanSpeed(IntEnum):
    AUTO = 0x00
    MIN = 0x01
    MID = 0x02
    MAX = 0x03

class Mode(IntEnum):
    FAN = 0x00
    COOL = 0x01
    HEAT = 0x02
    AUTO = 0x03
    DRY = 0x04

class Limits(IntEnum):
    OFF = 0x00
    ONLY_VERTICAL = 0x01

class CommandType(IntEnum):
    XZ1 = 0x10
    STATE = 0x22

class PayloadType(IntEnum):
    REQUEST = 0x14
    RESPONSE = 0x15

@dataclass
class State:
    """Device state structure."""
    current_temperature: int = 21
    target_temperature: int = 21
    fan_speed: FanSpeed = FanSpeed.AUTO
    mode: Mode = Mode.FAN
    health: bool = False
    limits: Limits = Limits.OFF
    power: bool = False

class HaierProtocol:
    """Protocol handler for Haier AC communication."""
    
    def __init__(self, mac_address: str):
        """Initialize protocol handler."""
        # MAC address should be 12 hex chars, uppercase
        self.mac = mac_address.upper().replace(':', '').replace('-', '')
        if len(self.mac) != 12:
            raise ValueError(f"Invalid MAC address length: {mac_address}")
        self.seq = 0
        
    def _get_next_seq(self) -> int:
        """Get next sequence number."""
        seq = self.seq
        self.seq = (self.seq + 1) % 256
        return seq
    
    def _mac_to_bytes(self) -> bytes:
        """Convert MAC address to protocol format (12 chars + 4 zeros)."""
        # MAC as ASCII bytes + 4 zero bytes
        mac_bytes = self.mac.encode('ascii')
        return mac_bytes + b'\x00' * 4
    
    def _checksum(self, data: bytes) -> int:
        """Calculate checksum for command data."""
        # From raw-commands.ts: appendChecksum function
        # Sum of hex digits with alternating weights 16 and 1
        hex_str = data.hex()
        total = 0
        for i, char in enumerate(hex_str):
            value = int(char, 16)
            if i % 2 == 0:  # even position (0-indexed)
                total += value * 16
            else:  # odd position
                total += value
        checksum = total - 2 * 255
        return checksum & 0xFF
    
    def create_hello_packet(self) -> bytes:
        """Create hello packet (before init)."""
        seq = self._get_next_seq()
        
        # Header: 00 00 27 14 00 00 00 00
        header = b'\x00\x00\x27\x14\x00\x00\x00\x00'
        
        # 16 zero bytes
        zero16 = b'\x00' * 16
        
        # Another 16 zero bytes  
        zero16_2 = b'\x00' * 16
        
        # MAC address (12 chars + 4 zeros)
        mac_bytes = self._mac_to_bytes()
        
        # Another 16 zero bytes
        zero16_3 = b'\x00' * 16
        
        # Order byte (sequence)
        order_byte = seq.to_bytes(1, 'big')
        order_part = b'\x00\x00\x00' + order_byte
        
        # Command length and command
        command = b'\xff\xff\x0a\x00\x00\x00\x00\x00\x00\x01\x4d\x01\x59'  # hello()
        cmd_len = len(command)
        len_part = b'\x00\x00\x00' + cmd_len.to_bytes(1, 'big')
        
        # Build packet
        packet = (
            header + 
            zero16 + 
            zero16_2 + 
            mac_bytes +
            zero16_3 +
            order_part +
            len_part +
            command
        )
        
        return packet
    
    def create_init_packet(self) -> bytes:
        """Create init packet."""
        seq = self._get_next_seq()
        
        header = b'\x00\x00\x27\x14\x00\x00\x00\x00'
        zero16 = b'\x00' * 16
        zero16_2 = b'\x00' * 16
        mac_bytes = self._mac_to_bytes()
        zero16_3 = b'\x00' * 16
        order_part = b'\x00\x00\x00' + seq.to_bytes(1, 'big')
        
        command = b'\xff\xff\x08\x00\x00\x00\x00\x00\x00\x73\x7b'  # init()
        cmd_len = len(command)
        len_part = b'\x00\x00\x00' + cmd_len.to_bytes(1, 'big')
        
        packet = (
            header + 
            zero16 + 
            zero16_2 + 
            mac_bytes +
            zero16_3 +
            order_part +
            len_part +
            command
        )
        
        return packet
    
    def create_on_packet(self) -> bytes:
        """Create power on packet."""
        seq = self._get_next_seq()
        
        header = b'\x00\x00\x27\x14\x00\x00\x00\x00'
        zero16 = b'\x00' * 16
        zero16_2 = b'\x00' * 16
        mac_bytes = self._mac_to_bytes()
        zero16_3 = b'\x00' * 16
        order_part = b'\x00\x00\x00' + seq.to_bytes(1, 'big')
        
        command = b'\xff\xff\x0a\x00\x00\x00\x00\x00\x00\x01\x4d\x02\x5a'  # on()
        cmd_len = len(command)
        len_part = b'\x00\x00\x00' + cmd_len.to_bytes(1, 'big')
        
        packet = (
            header + 
            zero16 + 
            zero16_2 + 
            mac_bytes +
            zero16_3 +
            order_part +
            len_part +
            command
        )
        
        return packet
    
    def create_off_packet(self) -> bytes:
        """Create power off packet."""
        seq = self._get_next_seq()
        
        header = b'\x00\x00\x27\x14\x00\x00\x00\x00'
        zero16 = b'\x00' * 16
        zero16_2 = b'\x00' * 16
        mac_bytes = self._mac_to_bytes()
        zero16_3 = b'\x00' * 16
        order_part = b'\x00\x00\x00' + seq.to_bytes(1, 'big')
        
        command = b'\xff\xff\x0a\x00\x00\x00\x00\x00\x00\x01\x4d\x03\x5b'  # off()
        cmd_len = len(command)
        len_part = b'\x00\x00\x00' + cmd_len.to_bytes(1, 'big')
        
        packet = (
            header + 
            zero16 + 
            zero16_2 + 
            mac_bytes +
            zero16_3 +
            order_part +
            len_part +
            command
        )
        
        return packet
    
    def create_set_state_packet(self, state: State) -> bytes:
        """Create set state packet."""
        seq = self._get_next_seq()
        
        header = b'\x00\x00\x27\x14\x00\x00\x00\x00'
        zero16 = b'\x00' * 16
        zero16_2 = b'\x00' * 16
        mac_bytes = self._mac_to_bytes()
        zero16_3 = b'\x00' * 16
        order_part = b'\x00\x00\x00' + seq.to_bytes(1, 'big')
        
        # Build command according to setState() in raw-commands.ts
        # Start with: ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00
        command = bytearray([
            0xff, 0xff, 0x22, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x01, 0x4d, 0x5f, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ])
        
        # Add mode: 00 0{mode}
        command.extend([0x00, state.mode])
        
        # Add fan speed: 00 0{fanSpeed}
        command.extend([0x00, state.fan_speed])
        
        # Add limits: 00 0{limits}
        command.extend([0x00, state.limits])
        
        # Add power: 00 0{Number(state.health) ? 9 : 1}
        power_byte = 0x09 if state.health else 0x01
        command.extend([0x00, power_byte])
        
        # Add health: 00 0{Number(state.health)}
        health_byte = 0x01 if state.health else 0x00
        command.extend([0x00, health_byte])
        
        # Add zeros: 00 00
        command.extend([0x00, 0x00])
        
        # Add target temperature: 00 0{(targetTemperature - 16).toString(16)}
        temp_offset = state.target_temperature - 16
        if temp_offset < 0 or temp_offset > 15:
            raise ValueError(f"Target temperature out of range: {state.target_temperature}")
        command.extend([0x00, temp_offset])
        
        # Calculate checksum
        checksum = self._checksum(bytes(command))
        command.append(checksum)
        
        cmd_len = len(command)
        len_part = b'\x00\x00\x00' + cmd_len.to_bytes(1, 'big')
        
        packet = (
            header + 
            zero16 + 
            zero16_2 + 
            mac_bytes +
            zero16_3 +
            order_part +
            len_part +
            bytes(command)
        )
        
        return packet
    
    def parse_response(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse response from device using the same logic as TheParser."""
        results = []
        
        if len(data) < 4:
            return results
        
        i = 0
        while i < len(data):
            # Look for start of packet: 00 00 27 15 (response)
            if i + 4 <= len(data) and data[i:i+2] == b'\x00\x00' and data[i+2] == 0x27 and data[i+3] == 0x15:
                # This is a response packet
                try:
                    result = self._parse_packet(data, i)
                    if result:
                        results.append(result)
                        # Move i to end of this packet
                        i = result.get('end_index', i + 1)
                        continue
                except Exception as e:
                    _LOGGER.debug(f"Failed to parse packet at index {i}: {e}")
            
            i += 1
        
        return results
    
    def _parse_packet(self, data: bytes, start_idx: int) -> Optional[Dict[str, Any]]:
        """Parse a single packet starting at start_idx."""
        idx = start_idx
        
        # Minimum packet size check
        if len(data) - idx < 100:  # Rough estimate
            return None
        
        # Skip header (00 00 27 15 00 00 00 00)
        idx += 8
        
        # Skip 16 zero bytes (res_start_zero4)
        idx += 16
        
        # Skip another 16 zero bytes (first_zero)
        idx += 16
        
        # Skip another 16 zero bytes (second_zero)
        idx += 16
        
        # MAC address (12 chars + 4 zeros)
        mac_bytes = data[idx:idx+16]
        mac_ascii = mac_bytes[:12].decode('ascii', errors='ignore')
        idx += 16
        
        # Skip 16 zero bytes (third_zero)
        idx += 16
        
        # Scan command length section (7 bytes)
        if idx + 7 > len(data):
            return None
            
        # Byte 3 of this section is sequence number
        seq = data[idx + 3]
        
        # Byte 7 is command length
        cmd_len = data[idx + 6]
        idx += 7
        
        # Command data
        if idx + cmd_len > len(data):
            return None
            
        command = data[idx:idx+cmd_len]
        idx += cmd_len
        
        # Parse command if it's a state command (0x22)
        if cmd_len >= 3 and command[0] == 0xff and command[1] == 0xff and command[2] == 0x22:
            state = self._parse_state_command(command)
            return {
                'type': PayloadType.RESPONSE,
                'seq': seq,
                'mac': mac_ascii,
                'command_type': CommandType.STATE,
                'state': state,
                'end_index': idx
            }
        
        return {
            'type': PayloadType.RESPONSE,
            'seq': seq,
            'mac': mac_ascii,
            'command_type': command[2] if len(command) > 2 else None,
            'end_index': idx
        }
    
    def _parse_state_command(self, command: bytes) -> State:
        """Parse state command (0x22 type)."""
        if len(command) < 40:
            raise ValueError("State command too short")
        
        # Parse according to stateParser in parsers.ts
        # Skip to position where state data starts (after 0x22 command header)
        
        # In parsers.ts, stateParser starts at byte 22 (0-indexed) of the command
        # But looking at setState, the actual state data starts earlier
        
        # Simpler approach: extract known positions
        state = State()
        
        # Current temperature is at position 12-13 (16-bit big endian)
        if len(command) >= 14:
            state.current_temperature = struct.unpack_from('>H', command, 12)[0]
        
        # Mode at position 30-31
        if len(command) >= 32:
            state.mode = struct.unpack_from('>H', command, 30)[0]
        
        # Fan speed at position 32-33
        if len(command) >= 34:
            state.fan_speed = struct.unpack_from('>H', command, 32)[0]
        
        # Limits at position 34-35
        if len(command) >= 36:
            state.limits = struct.unpack_from('>H', command, 34)[0]
        
        # Power at position 36-37
        if len(command) >= 38:
            power_val = struct.unpack_from('>H', command, 36)[0]
            state.power = bool(power_val % 2)
        
        # Health at position 38-39
        if len(command) >= 40:
            health_val = struct.unpack_from('>H', command, 38)[0]
            state.health = bool(health_val % 2)
        
        # Target temperature at position 42-43 (but needs +16)
        if len(command) >= 44:
            temp_offset = struct.unpack_from('>H', command, 42)[0]
            state.target_temperature = temp_offset + 16
        
        return state