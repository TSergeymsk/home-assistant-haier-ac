"""Device class for Haier AC."""
import asyncio
import logging
import socket
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .protocol import HaierProtocol, State, FanSpeed, Mode, Limits

_LOGGER = logging.getLogger(__name__)


def test_connection(ip_address: str) -> bool:
    """Test TCP connection to Haier device on port 56800."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        
        result = sock.connect_ex((ip_address, 56800))
        sock.close()
        
        if result == 0:
            _LOGGER.debug(f"Successfully connected to {ip_address}:56800")
            return True
        else:
            _LOGGER.debug(f"Failed to connect to {ip_address}:56800 (error code: {result})")
            return False
            
    except Exception as ex:
        _LOGGER.debug(f"Connection test failed for {ip_address}:56800: {ex}")
        return False


class HaierDevice:
    """Representation of a Haier AC device."""
    
    def __init__(self, hass, ip_address, mac, name, health_mode=False, health_mode_type="switch", timeout=5000):
        """Initialize the device."""
        self.hass = hass
        self.ip_address = ip_address
        self.port = 56800
        self.name = name
        self._health_mode = health_mode
        self._health_mode_type = health_mode_type
        self.timeout = timeout / 1000.0
        
        # Protocol handler
        self.protocol = HaierProtocol(mac)
        
        # Current state
        self._state = State()
        self._state_lock = asyncio.Lock()
        
        # Connection
        self._reader = None
        self._writer = None
        self._connected = False
        self._last_update = None
        self._update_interval = timedelta(seconds=30)
        
        # Response buffer
        self._response_buffer = bytearray()
        self._expected_seq = None
        self._response_event = asyncio.Event()
        self._last_response = None
        
        _LOGGER.info(f"Initialized Haier device {name} at {ip_address}:{self.port}")

    async def async_connect(self):
        """Connect to the device and perform handshake."""
        try:
            # Test connection first
            if not await self.hass.async_add_executor_job(test_connection, self.ip_address):
                raise ConnectionError(f"Cannot connect to device at {self.ip_address}:{self.port}")
            
            # Establish TCP connection
            await self._establish_connection()
            
            # Start listening for responses
            asyncio.create_task(self._listen_for_responses())
            
            # Perform handshake: hello -> init
            await self._send_packet(self.protocol.create_hello_packet())
            await asyncio.sleep(0.1)
            
            await self._send_packet(self.protocol.create_init_packet())
            await asyncio.sleep(0.1)
            
            # Get initial state
            await self.update()
            
            self._connected = True
            _LOGGER.info(f"Connected to Haier device {self.name} at {self.ip_address}:{self.port}")
            
        except Exception as ex:
            _LOGGER.error(f"Failed to connect to device: {ex}")
            await self._close_connection()
            raise

    async def _establish_connection(self):
        """Establish TCP connection."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip_address, self.port),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise ConnectionError(f"Connection timeout to {self.ip_address}:{self.port}")
        except Exception as ex:
            raise ConnectionError(f"Failed to establish connection: {ex}")

    async def async_disconnect(self):
        """Disconnect from the device."""
        await self._close_connection()
        self._connected = False
        _LOGGER.info(f"Disconnected from Haier device {self.name}")

    async def _close_connection(self):
        """Close TCP connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except:
                pass
        self._reader = None
        self._writer = None

    async def _send_packet(self, packet: bytes) -> bool:
        """Send raw packet to device."""
        if not self._writer:
            raise ConnectionError("Not connected to device")
        
        try:
            self._writer.write(packet)
            await self._writer.drain()
            _LOGGER.debug(f"Sent packet of length {len(packet)}")
            return True
        except Exception as ex:
            _LOGGER.error(f"Failed to send packet: {ex}")
            self._connected = False
            raise

    async def _listen_for_responses(self):
        """Listen for responses from device."""
        while self._writer and not self._writer.is_closing():
            try:
                data = await asyncio.wait_for(
                    self._reader.read(1024),
                    timeout=self.timeout
                )
                
                if not data:
                    # Connection closed
                    break
                
                self._response_buffer.extend(data)
                
                # Parse any complete packets in buffer
                while self._response_buffer:
                    parsed = self.protocol.parse_response(bytes(self._response_buffer))
                    if parsed:
                        for result in parsed:
                            _LOGGER.debug(f"Parsed response: seq={result.get('seq')}, type={result.get('command_type')}")
                            
                            if 'state' in result:
                                async with self._state_lock:
                                    self._state = result['state']
                                    self._last_update = datetime.now()
                                    _LOGGER.debug(f"State updated: {self._state}")
                            
                            # Signal if this was the expected response
                            if (self._expected_seq is not None and 
                                result.get('seq') == self._expected_seq):
                                self._last_response = result
                                self._response_event.set()
                        
                        # Remove processed data
                        end_idx = max(r.get('end_index', 0) for r in parsed)
                        if end_idx > 0 and end_idx <= len(self._response_buffer):
                            self._response_buffer = self._response_buffer[end_idx:]
                        else:
                            # Clear buffer if we can't determine end
                            self._response_buffer.clear()
                    else:
                        # No complete packet yet, wait for more data
                        break
                        
            except asyncio.TimeoutError:
                # No data received, continue listening
                continue
            except Exception as ex:
                _LOGGER.error(f"Error listening for responses: {ex}")
                break
        
        _LOGGER.debug("Stopped listening for responses")

    async def _send_command(self, packet_generator, wait_for_response=True, timeout=2.0):
        """Send command and optionally wait for response."""
        if not self._connected:
            await self.async_connect()
        
        # Generate packet (this will increment seq in protocol)
        packet = packet_generator()
        
        # Get expected sequence number (already incremented by protocol)
        expected_seq = self.protocol.seq - 1
        
        if wait_for_response:
            self._expected_seq = expected_seq
            self._response_event.clear()
            self._last_response = None
        
        # Send packet
        await self._send_packet(packet)
        
        if wait_for_response:
            # Wait for response
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
                return self._last_response
            except asyncio.TimeoutError:
                _LOGGER.warning(f"Timeout waiting for response to seq {expected_seq}")
                return None
            finally:
                self._expected_seq = None
        
        return None

    async def update(self):
        """Update device state by requesting current state."""
        # We can't directly request state, but setState with current values
        # should return current state
        if not self._connected:
            try:
                await self.async_connect()
            except Exception:
                return
        
        async with self._state_lock:
            current_state = self._state
        
        # Send setState with current values to get response
        try:
            packet = self.protocol.create_set_state_packet(current_state)
            response = await self._send_command(lambda: packet, wait_for_response=True, timeout=3.0)
            
            if response and 'state' in response:
                async with self._state_lock:
                    self._state = response['state']
                    self._last_update = datetime.now()
                    _LOGGER.debug(f"State updated from device: {self._state}")
        except Exception as ex:
            _LOGGER.warning(f"Failed to update state: {ex}")

    # Command methods matching haier-ac-remote API
    async def on(self):
        """Turn device on."""
        response = await self._send_command(self.protocol.create_on_packet)
        if response:
            async with self._state_lock:
                self._state.power = True
                self._last_update = datetime.now()
        return response is not None

    async def off(self):
        """Turn device off."""
        response = await self._send_command(self.protocol.create_off_packet)
        if response:
            async with self._state_lock:
                self._state.power = False
                self._last_update = datetime.now()
        return response is not None

    async def change_state(self, new_state: Dict[str, Any]):
        """Change device state (partial update)."""
        async with self._state_lock:
            # Create updated state
            updated_state = State(
                current_temperature=self._state.current_temperature,
                target_temperature=new_state.get('target_temperature', self._state.target_temperature),
                fan_speed=new_state.get('fan_speed', self._state.fan_speed),
                mode=new_state.get('mode', self._state.mode),
                health=new_state.get('health', self._state.health),
                limits=new_state.get('limits', self._state.limits),
                power=self._state.power  # Keep current power state
            )
            
            # Ensure power is on if we're changing state
            if not updated_state.power and any(k in new_state for k in ['mode', 'fan_speed', 'target_temperature', 'limits', 'health']):
                await self.on()
                updated_state.power = True
        
        # Send setState command
        packet = self.protocol.create_set_state_packet(updated_state)
        response = await self._send_command(lambda: packet, wait_for_response=True)
        
        if response and 'state' in response:
            async with self._state_lock:
                self._state = response['state']
                self._last_update = datetime.now()
            return True
        
        return False

    # Property accessors for Home Assistant
    @property
    def power(self):
        return self._state.power
        
    @property
    def mode(self):
        return self._state.mode
        
    @property
    def target_temperature(self):
        return self._state.target_temperature
        
    @property
    def current_temperature(self):
        return self._state.current_temperature
        
    @property
    def fan_speed(self):
        return self._state.fan_speed
        
    @property
    def swing_mode(self):
        return self._state.limits  # limits maps to swing mode
        
    @property
    def health_mode(self):
        return self._state.health
        
    @property
    def mac(self):
        return self.protocol.mac
        
    @property
    def available(self):
        if self._last_update is None:
            return False
        return datetime.now() - self._last_update < timedelta(minutes=5)
        
    @property
    def is_connected(self):
        return self._connected and self._writer is not None and not self._writer.is_closing()