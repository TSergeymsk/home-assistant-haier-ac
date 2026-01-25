"""Climate platform for Haier AC integration."""
import logging
from typing import Any

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
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.const import UnitOfTemperature 
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import HaierEntity
from .protocol import Mode, FanSpeed, Limits

_LOGGER = logging.getLogger(__name__)

# Mapping between HA modes and Haier modes
HA_TO_HAIER_MODE = {
    HVACMode.OFF: None,  # Special case - handled by power
    HVACMode.AUTO: Mode.AUTO,
    HVACMode.COOL: Mode.COOL,
    HVACMode.HEAT: Mode.HEAT,
    HVACMode.DRY: Mode.DRY,
    HVACMode.FAN_ONLY: Mode.FAN,
}

HAIER_TO_HA_MODE = {
    Mode.AUTO: HVACMode.AUTO,
    Mode.COOL: HVACMode.COOL,
    Mode.HEAT: HVACMode.HEAT,
    Mode.DRY: HVACMode.DRY,
    Mode.FAN: HVACMode.FAN_ONLY,
}

# Fan speed mapping
HA_TO_HAIER_FAN = {
    FAN_AUTO: FanSpeed.AUTO,
    FAN_LOW: FanSpeed.MIN,
    FAN_MEDIUM: FanSpeed.MID,
    FAN_HIGH: FanSpeed.MAX,
}

HAIER_TO_HA_FAN = {
    FanSpeed.AUTO: FAN_AUTO,
    FanSpeed.MIN: FAN_LOW,
    FanSpeed.MID: FAN_MEDIUM,
    FanSpeed.MAX: FAN_HIGH,
}

# Swing mode mapping
HA_TO_HAIER_SWING = {
    SWING_OFF: Limits.OFF,
    SWING_VERTICAL: Limits.ONLY_VERTICAL,
}

HAIER_TO_HA_SWING = {
    Limits.OFF: SWING_OFF,
    Limits.ONLY_VERTICAL: SWING_VERTICAL,
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
    
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, 
                        HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY]
    _attr_fan_modes = list(HA_TO_HAIER_FAN.keys())
    _attr_swing_modes = list(HA_TO_HAIER_SWING.keys())
    _attr_target_temperature_step = 1.0
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
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
        return self._device.current_temperature
    
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._device.target_temperature
    
    @property
    def hvac_mode(self):
        """Return current HVAC mode."""
        if not self._device.power:
            return HVACMode.OFF
        
        mode = self._device.mode
        return HAIER_TO_HA_MODE.get(mode, HVACMode.AUTO)
    
    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        if not self._device.power:
            return HVACAction.OFF
        
        mode = self._device.mode
        if mode == Mode.COOL:
            return HVACAction.COOLING
        elif mode == Mode.HEAT:
            return HVACAction.HEATING
        elif mode == Mode.DRY:
            return HVACAction.DRYING
        elif mode == Mode.FAN:
            return HVACAction.FAN
        else:
            return HVACAction.IDLE
    
    @property
    def fan_mode(self):
        """Return the fan mode."""
        fan_speed = self._device.fan_speed
        return HAIER_TO_HA_FAN.get(fan_speed, FAN_AUTO)
    
    @property
    def swing_mode(self):
        """Return the swing mode."""
        swing = self._device.swing_mode
        return HAIER_TO_HA_SWING.get(swing, SWING_OFF)
    
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self._device.change_state({
                'target_temperature': temperature
            })
            self.async_write_ha_state()
    
    async def async_set_hvac_mode(self, hvac_mode):
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._device.off()
        else:
            haier_mode = HA_TO_HAIER_MODE.get(hvac_mode)
            if haier_mode is not None:
                await self._device.change_state({
                    'mode': haier_mode
                })
        self.async_write_ha_state()
    
    async def async_set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        haier_fan = HA_TO_HAIER_FAN.get(fan_mode)
        if haier_fan is not None:
            await self._device.change_state({
                'fan_speed': haier_fan
            })
        self.async_write_ha_state()
    
    async def async_set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        haier_swing = HA_TO_HAIER_SWING.get(swing_mode)
        if haier_swing is not None:
            await self._device.change_state({
                'limits': haier_swing
            })
        self.async_write_ha_state()