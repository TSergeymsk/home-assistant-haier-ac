"""Device class for Haier AC."""
import asyncio
import logging
from typing import Optional, Dict, Any
import socket
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)


def test_connection(ip_address: str) -> bool:
    """Test connection to Haier device.
    
    Вместо простой проверки порта, попробуем отправить реальный запрос к устройству.
    """
    try:
        # Пробуем отправить CoAP запрос (кондиционеры Haier обычно используют CoAP на порту 5683)
        # или использовать HTTP, если устройство поддерживает
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        
        # CoAP ping (пустой запрос)
        coap_ping = bytes.fromhex('40000000')  # Простой CoAP ping
        
        sock.sendto(coap_ping, (ip_address, 5683))
        
        # Пробуем получить ответ
        try:
            data, addr = sock.recvfrom(1024)
            _LOGGER.debug(f"Received response from {ip_address}: {data.hex()}")
            return True
        except socket.timeout:
            # Если нет ответа на CoAP, пробуем HTTP
            _LOGGER.debug(f"No CoAP response, trying HTTP on {ip_address}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            result = sock.connect_ex((ip_address, 80))
            sock.close()
            return result == 0
    
    except Exception as ex:
        _LOGGER.debug(f"Connection test failed: {ex}")
        return False


class HaierDevice:
    """Representation of a Haier AC device based on haier-ac-remote library."""
    
    def __init__(self, hass, ip_address, mac, name, health_mode=False, health_mode_type="switch", timeout=3000):
        """Initialize the device."""
        self.hass = hass
        self.ip_address = ip_address
        self.mac = mac.lower().replace(':', '').replace('-', '')
        self.name = name
        self._health_mode = health_mode
        self._health_mode_type = health_mode_type
        self.timeout = timeout / 1000.0  # Convert ms to seconds
        
        # Device state (initialize with defaults)
        self._power = False
        self._mode = 1  # AUTO
        self._target_temperature = 24.0
        self._current_temperature = 24.0
        self._fan_speed = 0  # AUTO
        self._limits = 0  # OFF - swing mode
        self._health = False
        
        # Connection state
        self._connected = False
        self._last_update = None
        self._update_interval = timedelta(seconds=30)
        
        # Mode mapping
        self.MODE_MAP = {
            0: "off",
            1: "auto",
            2: "cool",
            3: "heat",
            4: "fan",
            5: "dry"
        }
        
        self.FAN_SPEED_MAP = {
            0: "auto",
            1: "low",
            2: "medium",
            3: "high"
        }
        
        _LOGGER.info(f"Initialized Haier device {name} at {ip_address}")

    async def async_connect(self):
        """Connect to the device."""
        try:
            # Test connection first
            if not await self.hass.async_add_executor_job(test_connection, self.ip_address):
                raise ConnectionError(f"Cannot connect to device at {self.ip_address}")
            
            # Try to get initial state
            await self._update_state()
            self._connected = True
            _LOGGER.info(f"Connected to Haier device {self.name} at {self.ip_address}")
            
        except Exception as ex:
            _LOGGER.error(f"Failed to connect to device: {ex}")
            raise

    async def async_disconnect(self):
        """Disconnect from the device."""
        self._connected = False
        _LOGGER.info(f"Disconnected from Haier device {self.name}")

    async def _send_command(self, command: Dict[str, Any]) -> bool:
        """Send command to Haier device.
        
        This is a simplified implementation. In real implementation,
        you would use the actual protocol (CoAP/HTTP) based on haier-ac-remote.
        """
        try:
            # Здесь должна быть реальная реализация отправки команд
            # На основе анализа haier.ts, устройства Haier используют CoAP
            
            # Временная реализация - симуляция работы
            _LOGGER.debug(f"Sending command to {self.ip_address}: {command}")
            
            # Имитация задержки сети
            await asyncio.sleep(0.1)
            
            # Обновляем локальное состояние на основе команды
            if 'power' in command:
                self._power = command['power']
            
            if 'mode' in command:
                self._mode = command['mode']
            
            if 'targetTemperature' in command:
                self._target_temperature = float(command['targetTemperature'])
            
            if 'fanSpeed' in command:
                self._fan_speed = command['fanSpeed']
            
            if 'limits' in command:
                self._limits = command['limits']
            
            if 'health' in command:
                self._health = command['health']
            
            self._last_update = datetime.now()
            return True
            
        except Exception as ex:
            _LOGGER.error(f"Failed to send command: {ex}")
            return False

    async def _update_state(self):
        """Update device state from actual device."""
        try:
            # Здесь должна быть реальная реализация получения состояния
            # Временная реализация - возвращаем текущее состояние
            
            # Имитация получения данных с устройства
            await asyncio.sleep(0.05)
            
            # Если устройство выключено, некоторые значения могут быть недоступны
            if not self._power:
                self._current_temperature = 25.0  # Примерное значение
            else:
                # Имитация изменения температуры
                # В реальной реализации здесь нужно получать реальные данные
                pass
            
            self._last_update = datetime.now()
            
        except Exception as ex:
            _LOGGER.error(f"Failed to update state: {ex}")
            raise

    async def update(self):
        """Public method to update device state."""
        if not self._connected:
            await self.async_connect()
        
        if (self._last_update is None or 
            datetime.now() - self._last_update > self._update_interval):
            await self._update_state()

    async def set_power(self, state: bool):
        """Turn device on/off."""
        command = {'power': state}
        if not state:
            # При выключении также сбрасываем режим
            command['mode'] = 1  # AUTO
        return await self._send_command(command)

    async def set_mode(self, mode: int):
        """Set HVAC mode (1=auto, 2=cool, 3=heat, 4=fan, 5=dry)."""
        if mode not in self.MODE_MAP:
            raise ValueError(f"Invalid mode: {mode}")
        
        command = {'mode': mode}
        if mode != 0:  # Если не выключение
            command['power'] = True
        return await self._send_command(command)

    async def set_temperature(self, temperature: float):
        """Set target temperature."""
        if temperature < 16 or temperature > 30:
            raise ValueError(f"Temperature out of range: {temperature}")
        
        command = {'targetTemperature': temperature}
        return await self._send_command(command)

    async def set_fan_speed(self, speed: int):
        """Set fan speed (0=auto, 1=low, 2=medium, 3=high)."""
        if speed not in self.FAN_SPEED_MAP:
            raise ValueError(f"Invalid fan speed: {speed}")
        
        command = {'fanSpeed': speed}
        return await self._send_command(command)

    async def set_swing_mode(self, mode: int):
        """Set swing mode (0=off, 1=vertical only)."""
        command = {'limits': mode}
        return await self._send_command(command)

    async def set_health_mode(self, state: bool):
        """Set health mode."""
        command = {'health': state}
        return await self._send_command(command)

    @property
    def power(self):
        """Return power state."""
        return self._power
        
    @property
    def mode(self):
        """Return current mode."""
        return self._mode
        
    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._target_temperature
        
    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_temperature
        
    @property
    def fan_speed(self):
        """Return fan speed."""
        return self._fan_speed
        
    @property
    def swing_mode(self):
        """Return swing mode."""
        return self._limits
        
    @property
    def health_mode(self):
        """Return health mode state."""
        return self._health
        
    @property
    def available(self):
        """Return if device is available."""
        if self._last_update is None:
            return False
        return datetime.now() - self._last_update < timedelta(minutes=5)