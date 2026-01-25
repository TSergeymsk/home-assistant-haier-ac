"""Switch platform for Haier AC integration."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_HEALTH_MODE, CONF_HEALTH_MODE_TYPE
from .entity import HaierEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier AC switch entities from a config entry."""
    device = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Add health mode switch if configured
    if entry.data.get(CONF_HEALTH_MODE) and entry.data.get(CONF_HEALTH_MODE_TYPE) == "switch":
        entities.append(HaierHealthModeSwitch(device, entry))
    
    # Add other switches here (e.g., eco mode, turbo mode, etc.)
    
    if entities:
        async_add_entities(entities)


class HaierHealthModeSwitch(HaierEntity, SwitchEntity):
    """Representation of a Haier AC health mode switch."""
    
    def __init__(self, device, entry):
        """Initialize the switch."""
        super().__init__(device, entry)
        self._attr_unique_id = f"{device.mac}_health_mode"
        self._attr_name = f"{device.name} Health Mode"
        self._attr_icon = "mdi:leaf"
    
    @property
    def is_on(self):
        """Return True if health mode is enabled."""
        return self._device.health_mode
    
    async def async_turn_on(self, **kwargs):
        """Turn on health mode."""
        await self._device.set_health_mode(True)
        self.async_write_ha_state()
    
    async def async_turn_off(self, **kwargs):
        """Turn off health mode."""
        await self._device.set_health_mode(False)
        self.async_write_ha_state()