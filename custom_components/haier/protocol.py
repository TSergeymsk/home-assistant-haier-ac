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
    
    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate checksum for command data."""
        # From raw-commands.ts: appendChecksum function
        # Simple sum of bytes
        total = sum(data)
        checksum = total & 0xFF
        return checksum
    
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
        # hello(): ff ff 0a 00 00 00 00 00 00 01 4d 01 59
        command = b'\xff\xff\x0a\x00\x00\x00\x00\x00\x00\x01\x4d\x01\x59'
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
        
        # init(): ff ff 08 00 00 00 00 00 00 73 7b
        command = b'\xff\xff\x08\x00\x00\x00\x00\x00\x00\x73\x7b'
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
        
        # on(): ff ff 0a 00 00 00 00 00 00 01 4d 02 5a
        command = b'\xff\xff\x0a\x00\x00\x00\x00\x00\x00\x01\x4d\x02\x5a'
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
        
        # off(): ff ff 0a 00 00 00 00 00 00 01 4d 03 5b
        command = b'\xff\xff\x0a\x00\x00\x00\x00\x00\x00\x01\x4d\x03\x5b'
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
        checksum = self._calculate_checksum(bytes(command))
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
        """Parse response from device using simplified logic."""
        results = []
        
        if len(data) < 4:
            return results
        
        i = 0
        while i < len(data):
            # Look for response packet marker: 00 00 27 15
            if i + 4 <= len(data) and data[i:i+4] == b'\x00\x00\x27\x15':
                # Try to parse this packet
                result = self._parse_packet_simple(data[i:])
                if result:
                    results.append(result)
                    # Skip ahead
                    i += result.get('packet_length', 100)
                    continue
            i += 1
        
        return results
    
    def _parse_packet_simple(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Simplified packet parser based on the logs."""
        if len(data) < 100:
            return None
        
        try:
            # Response packet structure:
            # 0-3: 00 00 27 15 (response marker)
            # 4-19: 16 zero bytes
            # 20-35: 16 zero bytes
            # 36-51: 16 zero bytes
            # 52-67: MAC address (12 chars + 4 zeros)
            # 68-83: 16 zero bytes
            # 84-90: sequence and length section
            #   87: sequence number
            #   90: command length
            # 91+: command data
            
            if data[0:4] != b'\x00\x00\x27\x15':
                return None
            
            # Extract MAC address (bytes 52-63)
            mac_bytes = data[52:64]
            mac = mac_bytes.decode('ascii', errors='ignore')
            
            # Extract sequence number (byte 87)
            seq = data[87]
            
            # Extract command length (byte 90)
            cmd_len = data[90]
            
            if cmd_len == 0 or 91 + cmd_len > len(data):
                return None
            
            # Extract command data
            command = data[91:91+cmd_len]
            
            # Parse command type
            cmd_type = None
            state_data = None
            
            if len(command) >= 3:
                # Check command type
                if command[0] == 0xff and command[1] == 0xff:
                    cmd_type = command[2]  # Command type byte
                    
                    # Try to parse state if it's a state command
                    if cmd_type == 0x22 and len(command) >= 44:
                        state_data = self._parse_state_command_simple(command)
            
            return {
                'seq': seq,
                'mac': mac,
                'command_type': cmd_type,
                'state': state_data,
                'packet_length': 91 + cmd_len
            }
            
        except Exception as ex:
            _LOGGER.debug(f"Failed to parse packet: {ex}")
            return None
    
    def _parse_state_command_simple(self, command: bytes) -> Optional[State]:
        """Parse state command (0x22 type) with simplified logic."""
        try:
            state = State()
            
            # Parse based on structure from parsers.ts
            # Assuming state data starts at byte 12 (0-indexed)
            
            # Current temperature (bytes 12-13, 16-bit big endian)
            if len(command) >= 14:
                state.current_temperature = struct.unpack_from('>H', command, 12)[0]
            
            # Mode (bytes 30-31)
            if len(command) >= 32:
                state.mode = struct.unpack_from('>H', command, 30)[0]
            
            # Fan speed (bytes 32-33)
            if len(command) >= 34:
                state.fan_speed = struct.unpack_from('>H', command, 32)[0]
            
            # Limits (bytes 34-35)
            if len(command) >= 36:
                state.limits = struct.unpack_from('>H', command, 34)[0]
            
            # Power (bytes 36-37)
            if len(command) >= 38:
                power_val = struct.unpack_from('>H', command, 36)[0]
                state.power = bool(power_val % 2)
            
            # Health (bytes 38-39)
            if len(command) >= 40:
                health_val = struct.unpack_from('>H', command, 38)[0]
                state.health = bool(health_val % 2)
            
            # Target temperature (bytes 42-43, needs +16)
            if len(command) >= 44:
                temp_offset = struct.unpack_from('>H', command, 42)[0]
                state.target_temperature = temp_offset + 16
            
            return state
            
        except Exception as ex:
            _LOGGER.debug(f"Failed to parse state: {ex}")
            return None