"""Climate platform for Haier AC integration."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
    FAN_AUTO,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    SWING_OFF,
    SWING_VERTICAL,
    SWING_HORIZONTAL,
    SWING_BOTH,
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ATTR_INSIDE_TEMPERATURE, ATTR_OUTSIDE_TEMPERATURE
from .entity import HaierEntity

_LOGGER = logging.getLogger(__name__)

# Haier specific constants
HAIER_FAN_SPEEDS = {
    FAN_AUTO: 0,
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3
}

HAIER_SWING_MODES = {
    SWING_OFF: 0,
    SWING_VERTICAL: 1,
    SWING_HORIZONTAL: 2,
    SWING_BOTH: 3
}

HAIER_HVAC_MODES = {
    HVACMode.OFF: 0,
    HVACMode.AUTO: 1,
    HVACMode.COOL: 2,
    HVACMode.HEAT: 3,
    HVACMode.DRY: 4,
    HVACMode.FAN_ONLY: 5
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Haier AC climate entity from a config entry."""
    device = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaierClimateEntity(device, entry)])


class HaierClimateEntity(HaierEntity, ClimateEntity):
    """Representation of a Haier AC climate entity."""
    
    _attr_hvac_modes = list(HAIER_HVAC_MODES.keys())
    _attr_fan_modes = list(HAIER_FAN_SPEEDS.keys())
    _attr_swing_modes = list(HAIER_SWING_MODES.keys())
    _attr_target_temperature_step = 1.0
    _attr_temperature_unit = TEMP_CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE |
        ClimateEntityFeature.FAN_MODE |
        ClimateEntityFeature.SWING_MODE |
        ClimateEntityFeature.TURN_OFF |
        ClimateEntityFeature.TURN_ON
    )
    
    def __init__(self, device, entry):
        """Initialize the climate entity."""
        super().__init__(device, entry)
        self._attr_unique_id = f"{device.mac}_climate"
        self._attr_name = device.name
        
    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._device.inside_temperature
    
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._device.target_temperature
    
    @property
    def hvac_mode(self):
        """Return current HVAC mode."""
        if not self._device.power:
            return HVACMode.OFF
        
        mode_map = {v: k for k, v in HAIER_HVAC_MODES.items()}
        return mode_map.get(self._device.mode, HVACMode.AUTO)
    
    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        if not self._device.power:
            return HVACAction.OFF
        
        # This should be based on actual device state
        if self._device.mode == 2:  # COOL
            return HVACAction.COOLING
        elif self._device.mode == 3:  # HEAT
            return HVACAction.HEATING
        elif self._device.mode == 4:  # DRY
            return HVACAction.DRYING
        elif self._device.mode == 5:  # FAN_ONLY
            return HVACAction.FAN
        else:
            return HVACAction.IDLE
    
    @property
    def fan_mode(self):
        """Return the fan mode."""
        mode_map = {v: k for k, v in HAIER_FAN_SPEEDS.items()}
        return mode_map.get(self._device.fan_speed, FAN_AUTO)
    
    @property
    def swing_mode(self):
        """Return the swing mode."""
        mode_map = {v: k for k, v in HAIER_SWING_MODES.items()}
        return mode_map.get(self._device.swing_mode, SWING_OFF)
    
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._device.set_temperature(temperature)
            self.async_write_ha_state()
    
    async def async_set_hvac_mode(self, hvac_mode):
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._device.set_power(False)
        else:
            if not self._device.power:
                await self._device.set_power(True)
            await self._device.set_mode(HAIER_HVAC_MODES[hvac_mode])
        self.async_write_ha_state()
    
    async def async_set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        await self._device.set_fan_speed(HAIER_FAN_SPEEDS[fan_mode])
        self.async_write_ha_state()
    
    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        await self._device.set_swing_mode(HAIER_SWING_MODES[swing_mode])
        self.async_write_ha_state()
    
    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = {
            ATTR_INSIDE_TEMPERATURE: self._device.inside_temperature,
            ATTR_OUTSIDE_TEMPERATURE: self._device.outside_temperature,
        }
        return attrs