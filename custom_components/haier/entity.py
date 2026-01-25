"""Base entity for Haier AC integration."""
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class HaierEntity(Entity):
    """Base class for Haier entities."""
    
    def __init__(self, device, entry):
        """Initialize the entity."""
        self._device = device
        self._entry = entry
        
    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.mac)},
            name=self._device.name,
            manufacturer="Haier",
            model="Air Conditioner",
            sw_version="1.0",
            configuration_url=f"http://{self._device.ip_address}",
        )
    
    @property
    def available(self) -> bool:
        """Return True if device is available."""
        # Implement actual availability check
        return True
    
    @property
    def should_poll(self) -> bool:
        """Return True if entity should be polled."""
        return True
    
    async def async_update(self):
        """Update entity state."""
        await self._device.update()