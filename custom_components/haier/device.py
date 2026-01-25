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
        
        # Response handling
        self._response_waiter = None
        self._expected_seq = None
        self._received_responses = {}
        
        _LOGGER.info(f"Initialized Haier device {name} at {ip_address}:{self.port}")

    async def async_connect(self):
        """Connect to the device using official protocol."""
        try:
            # Test connection first
            if not await self.hass.async_add_executor_job(test_connection, self.ip_address):
                raise ConnectionError(f"Cannot connect to device at {self.ip_address}:{self.port}")
            
            # Establish TCP connection
            await self._establish_connection()
            
            # Send hello packet and wait for response
            hello_packet = self.protocol.create_hello_packet()
            _LOGGER.debug(f"Sending hello packet: {hello_packet.hex()}")
            await self._send_raw_packet(hello_packet)
            
            # Wait for response (give it some time)
            await asyncio.sleep(1.0)
            
            # Send init packet
            init_packet = self.protocol.create_init_packet()
            _LOGGER.debug(f"Sending init packet: {init_packet.hex()}")
            await self._send_raw_packet(init_packet)
            
            await asyncio.sleep(1.0)
            
            self._connected = True
            _LOGGER.info(f"Connected to Haier device {self.name} using official protocol")
            
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
            _LOGGER.debug(f"Sent packet of length {len(packet)}")
        except Exception as ex:
            _LOGGER.error(f"Failed to send packet: {ex}")
            self._connected = False
            raise

    async def _send_and_wait(self, packet: bytes, seq: int, timeout: float = 2.0):
        """Send packet and wait for response with given sequence."""
        # Set up response waiter
        self._expected_seq = seq
        response_event = asyncio.Event()
        self._received_responses[seq] = {'event': response_event, 'data': None}
        
        try:
            # Send packet
            await self._send_raw_packet(packet)
            
            # Wait for response with timeout
            async with async_timeout.timeout(timeout):
                await response_event.wait()
            
            # Get response data
            response = self._received_responses[seq]['data']
            return response
            
        except asyncio.TimeoutError:
            _LOGGER.warning(f"Timeout waiting for response with seq {seq}")
            return None
        finally:
            # Clean up
            if seq in self._received_responses:
                del self._received_responses[seq]
            self._expected_seq = None

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
                
                _LOGGER.debug(f"Received {len(data)} bytes from device")
                
                # Parse responses
                responses = self.protocol.parse_response(data)
                
                for response in responses:
                    frame_type = response.get('type')
                    command = response.get('command')
                    _LOGGER.debug(f"Parsed response: type=0x{frame_type:02x}, command=0x{command:02x}")
                    
                    # ОТПРАВКА ACK В ОТВЕТ НА ПЕРВЫЙ ПАКЕТ (тип 0x04)
                    if frame_type == 0x04:  # ACK от устройства
                        _LOGGER.debug(f"Received ACK from device, sending response ACK")
                        try:
                            # Создаем и отправляем ответный ACK-пакет
                            # В данных ACK используем полученный ack_status (0x5a = 90)
                            ack_data = bytes([0x5a, 0x00])  # Простой ACK-ответ
                            ack_packet = self.protocol._build_frame(0x04, ack_data, with_crc=False)
                            await self._send_raw_packet(ack_packet)
                            _LOGGER.debug(f"Sent ACK response to device: {ack_packet.hex()}")
                        except Exception as ex:
                            _LOGGER.error(f"Failed to send ACK response: {ex}")
                    
                    # Update device state if we have state data
                    if frame_type == 0x06:  # State response
                        state_data = response.get('data', {})
                        if state_data:
                            async with self._state_lock:
                                # Update device state from parsed data
                                if 'power' in state_data:
                                    self._state.power = state_data['power']
                                if 'mode' in state_data:
                                    self._state.mode = state_data['mode']
                                if 'target_temperature' in state_data:
                                    self._state.target_temperature = state_data['target_temperature']
                                if 'current_temperature' in state_data:
                                    self._state.current_temperature = state_data['current_temperature']
                                if 'fan_speed' in state_data:
                                    self._state.fan_speed = state_data['fan_speed']
                                self._last_update = datetime.now()
                                _LOGGER.debug(f"State updated from response: power={self._state.power}, "
                                            f"mode={self._state.mode}, target_temp={self._state.target_temperature}, "
                                            f"current_temp={self._state.current_temperature}, fan_speed={self._state.fan_speed}")
                    
                    # Signal waiter if this is the expected response
                    if self._expected_seq is not None:
                        if self._expected_seq in self._received_responses:
                            self._received_responses[self._expected_seq]['data'] = response
                            self._received_responses[self._expected_seq]['event'].set()
                            _LOGGER.debug(f"Signaled waiter for seq {self._expected_seq}")
                
            except asyncio.CancelledError:
                _LOGGER.debug("Listening task cancelled")
                break
            except Exception as ex:
                _LOGGER.error(f"Error in listen task: {ex}")
                await asyncio.sleep(1)  # Avoid tight loop on error
        
        _LOGGER.debug("Stopped listening for responses")

    async def update(self):
        """Update device state by requesting current state."""
        if not self._connected:
            try:
                await self.async_connect()
            except Exception:
                return
        
        # Send status request
        try:
            # Use sequence number 10 for state requests
            packet = self.protocol.create_status_request_packet()
            response = await self._send_and_wait(packet, seq=10, timeout=3.0)
            
            if response:
                _LOGGER.debug(f"Update response received: {response}")
                # Check if response contains state data
                if 'data' in response:
                    state_data = response.get('data', {})
                    if state_data and ('power' in state_data or 'current_temperature' in state_data):
                        async with self._state_lock:
                            # Update state from response
                            if 'power' in state_data:
                                self._state.power = state_data['power']
                            if 'mode' in state_data:
                                self._state.mode = state_data['mode']
                            if 'target_temperature' in state_data:
                                self._state.target_temperature = state_data['target_temperature']
                            if 'current_temperature' in state_data:
                                self._state.current_temperature = state_data['current_temperature']
                            if 'fan_speed' in state_data:
                                self._state.fan_speed = state_data['fan_speed']
                            self._last_update = datetime.now()
                            _LOGGER.debug(f"State updated from update request: {self._state}")
        except Exception as ex:
            _LOGGER.warning(f"Failed to update state: {ex}")

    # Command methods matching haier-ac-remote API
    async def on(self):
        """Turn device on."""
        # Use sequence number 2 for on command
        response = await self._send_and_wait(self.protocol.create_on_packet(), seq=2)
        if response:
            async with self._state_lock:
                self._state.power = True
                self._last_update = datetime.now()
            return True
        return False

    async def off(self):
        """Turn device off."""
        # Use sequence number 3 for off command
        response = await self._send_and_wait(self.protocol.create_off_packet(), seq=3)
        if response:
            async with self._state_lock:
                self._state.power = False
                self._last_update = datetime.now()
            return True
        return False

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
        
        # Send setState command with sequence 20
        packet = self.protocol.create_set_state_packet(updated_state)
        response = await self._send_and_wait(packet, seq=20, timeout=3.0)
        
        if response:
            _LOGGER.debug(f"Change state response: {response}")
            # If response contains state data, update from it
            if 'data' in response:
                state_data = response.get('data', {})
                if state_data:
                    async with self._state_lock:
                        if 'power' in state_data:
                            self._state.power = state_data['power']
                        if 'mode' in state_data:
                            self._state.mode = state_data['mode']
                        if 'target_temperature' in state_data:
                            self._state.target_temperature = state_data['target_temperature']
                        if 'current_temperature' in state_data:
                            self._state.current_temperature = state_data['current_temperature']
                        if 'fan_speed' in state_data:
                            self._state.fan_speed = state_data['fan_speed']
                        self._last_update = datetime.now()
            return True
        
        return False

    # Health mode methods
    async def set_health_mode(self, enabled: bool):
        """Set health mode on or off."""
        async with self._state_lock:
            self._state.health = enabled
            self._last_update = datetime.now()
        
        # Send change_state with health mode update
        return await self.change_state({'health': enabled})

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