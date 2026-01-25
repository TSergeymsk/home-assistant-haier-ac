"""Device class for Haier AC."""
import binascii
import asyncio
import logging
import socket
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import async_timeout

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
        
        # Sequence number for commands (like in TS library)
        self._seq = 0
        
        # Response handling - simplified like TS library
        self._response_events = {}
        
        _LOGGER.info(f"Initialized Haier device {name} at {ip_address}:{self.port}")

    async def async_connect(self):
        """Connect to the device using official protocol."""
        try:
            # Test connection first
            if not await self.hass.async_add_executor_job(test_connection, self.ip_address):
                raise ConnectionError(f"Cannot connect to device at {self.ip_address}:{self.port}")
            
            # Establish TCP connection (no hello/init packets)
            await self._establish_connection()
            
            self._connected = True
            _LOGGER.info(f"Connected to Haier device {self.name}")
            
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
            # Start listening task
            self._listen_task = asyncio.create_task(self._listen_for_responses())
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
        # Cancel listening task
        if hasattr(self, '_listen_task'):
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except:
                pass
        self._reader = None
        self._writer = None

    async def _send_raw_packet(self, packet: bytes):
        """Send raw packet to device."""
        if not self._writer:
            raise ConnectionError("Not connected to device")
        
        try:
            self._writer.write(packet)
            await self._writer.drain()
            _LOGGER.debug(f"Sent packet: {binascii.hexlify(packet).decode()}")
        except Exception as ex:
            _LOGGER.error(f"Failed to send packet: {ex}")
            self._connected = False
            raise

    async def _send_request(self, create_command_func, timeout: float = 2.0):
        """Send request and wait for response (like in TS library)."""
        if not self._connected:
            try:
                await self.async_connect()
            except Exception as ex:
                _LOGGER.error(f"Failed to reconnect: {ex}")
                return False
        
        seq = self._seq
        self._seq = (self._seq + 1) % 256
        
        # Create command with sequence
        packet = create_command_func(seq)
        
        # Create event for waiting response
        response_event = asyncio.Event()
        self._response_events[seq] = {'event': response_event, 'data': None}
        
        try:
            # Send packet
            await self._send_raw_packet(packet)
            
            # Wait for response with timeout
            async with async_timeout.timeout(timeout):
                await response_event.wait()
            
            # Get response data
            response_data = self._response_events[seq]['data']
            return True if response_data else False
            
        except asyncio.TimeoutError:
            _LOGGER.warning(f"Timeout waiting for response with seq {seq}")
            # Try to reconnect like in TS library
            try:
                await self._close_connection()
                await self.async_connect()
            except:
                pass
            return False
        finally:
            # Clean up
            if seq in self._response_events:
                del self._response_events[seq]

    async def _listen_for_responses(self):
        """Listen for responses from device."""
        _LOGGER.debug("Starting to listen for responses")
        
        while True:
            try:
                if not self._reader:
                    await asyncio.sleep(0.1)
                    continue
                
                # Read data with timeout
                try:
                    async with async_timeout.timeout(1.0):
                        data = await self._reader.read(4096)
                except asyncio.TimeoutError:
                    # Timeout is normal, just continue listening
                    continue
                
                if not data:
                    # Connection closed
                    _LOGGER.debug("Connection closed by device")
                    break
                
                _LOGGER.debug(f"Received {len(data)} bytes from device: {binascii.hexlify(data).decode()}")
                
                # Parse responses
                responses = self.protocol.parse_response(data)
                
                for response in responses:
                    frame_type = response.get('type')
                    command = response.get('command')
                    seq = response.get('seq')
                    _LOGGER.debug(f"Parsed response: type=0x{frame_type:02x}, command=0x{command:02x}, seq={seq}")
                    
                    # Check if this is a state response
                    if response.get('command_type') == 0x22:  # State response
                        state_data = response.get('data', {})
                        if state_data:
                            async with self._state_lock:
                                # Update device state from parsed data
                                # Convert temperature like in TS library
                                if 'current_temperature' in state_data:
                                    self._state.current_temperature = state_data['current_temperature']
                                if 'target_temperature' in state_data:
                                    self._state.target_temperature = state_data['target_temperature'] + 16
                                if 'fan_speed' in state_data:
                                    self._state.fan_speed = state_data['fan_speed']
                                if 'mode' in state_data:
                                    self._state.mode = state_data['mode']
                                if 'health' in state_data:
                                    # Convert to boolean like in TS library
                                    self._state.health = bool(state_data['health'] % 2)
                                if 'power' in state_data:
                                    # Convert to boolean like in TS library
                                    self._state.power = bool(state_data['power'] % 2)
                                if 'limits' in state_data:
                                    self._state.limits = state_data['limits']
                                    
                                self._last_update = datetime.now()
                                _LOGGER.debug(f"State updated: {self._state}")
                    
                    # Signal waiter if this is the expected response
                    if seq is not None and seq in self._response_events:
                        self._response_events[seq]['data'] = response
                        self._response_events[seq]['event'].set()
                        _LOGGER.debug(f"Signaled waiter for seq {seq}")
            
            except asyncio.CancelledError:
                _LOGGER.debug("Listening task cancelled")
                break
            except Exception as ex:
                _LOGGER.error(f"Error in listen task: {ex}")
                await asyncio.sleep(1)  # Avoid tight loop on error
        
        _LOGGER.debug("Stopped listening for responses")

    async def update(self):
        """Update device state by requesting current state."""
        # Send status request using sequence
        try:
            packet = self.protocol.create_status_request_packet(self._seq)
            seq = self._seq
            self._seq = (self._seq + 1) % 256
            
            # Create event for waiting response
            response_event = asyncio.Event()
            self._response_events[seq] = {'event': response_event, 'data': None}
            
            await self._send_raw_packet(packet)
            
            # Wait for response
            try:
                async with async_timeout.timeout(3.0):
                    await response_event.wait()
                
                # Response will be processed in _listen_for_responses
                return True
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for status response")
                return False
            finally:
                if seq in self._response_events:
                    del self._response_events[seq]
                    
        except Exception as ex:
            _LOGGER.warning(f"Failed to update state: {ex}")
            return False

    # Command methods matching TS library
    async def on(self):
        """Turn device on."""
        def create_command(seq):
            return self.protocol.create_on_packet(seq)
        
        return await self._send_request(create_command)

    async def off(self):
        """Turn device off."""
        def create_command(seq):
            return self.protocol.create_off_packet(seq)
        
        return await self._send_request(create_command)

    async def change_state(self, new_state: Dict[str, Any]):
        """Change device state (partial update)."""
        # Ensure power is on if we're changing state (like in TS library)
        if not self._state.power:
            success = await self.on()
            if not success:
                return False
        
        # Apply state validation like in TS library
        if 'target_temperature' in new_state:
            target_temp = new_state['target_temperature']
            # Clamp temperature like in TS library
            if target_temp < 16:
                target_temp = 16
            if target_temp > 30:
                target_temp = 30
            target_temp = round(target_temp)
            new_state['target_temperature'] = target_temp
        
        # Merge with current state
        merged_state = State(
            current_temperature=self._state.current_temperature,
            target_temperature=new_state.get('target_temperature', self._state.target_temperature),
            fan_speed=new_state.get('fan_speed', self._state.fan_speed),
            mode=new_state.get('mode', self._state.mode),
            health=new_state.get('health', self._state.health),
            limits=new_state.get('limits', self._state.limits),
            power=True  # Already ensured to be on
        )
        
        def create_command(seq):
            return self.protocol.create_set_state_packet(merged_state, seq)
        
        return await self._send_request(create_command, timeout=3.0)

    async def set_health_mode(self, enabled: bool):
        """Set health mode on or off."""
        return await self.change_state({'health': enabled})

    async def hello(self):
        """Send hello packet (for debugging)."""
        def create_command(seq):
            return self.protocol.create_hello_packet(seq)
        
        return await self._send_request(create_command)

    async def init(self):
        """Send init packet (for debugging)."""
        def create_command(seq):
            return self.protocol.create_init_packet(seq)
        
        return await self._send_request(create_command)

    # Property accessors for Home Assistant
    @property
    def power(self):
        """Return power state."""
        return self._state.power
        
    @property
    def mode(self):
        """Return current mode."""
        return self._state.mode
        
    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._state.target_temperature
        
    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._state.current_temperature
        
    @property
    def fan_speed(self):
        """Return fan speed."""
        return self._state.fan_speed
        
    @property
    def swing_mode(self):
        """Return swing mode."""
        return self._state.limits
        
    @property
    def health_mode(self):
        """Return health mode state."""
        return self._state.health
        
    @property
    def mac(self):
        """Return MAC address."""
        return self.protocol.mac
        
    @property
    def available(self):
        """Return True if device is available."""
        if self._last_update is None:
            return False
        return datetime.now() - self._last_update < timedelta(minutes=5)
        
    @property
    def is_connected(self):
        """Return True if connected to device."""
        return self._connected and self._writer is not None and not self._writer.is_closing()