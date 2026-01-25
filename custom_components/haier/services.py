"""Services for Haier AC integration."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_setup_service_schema

from .const import DOMAIN, SERVICE_SET_FAN_SPEED, SERVICE_SET_SWING_MODE

async def async_setup_services(hass: HomeAssistant):
    """Set up services for Haier integration."""
    
    async def async_handle_set_fan_speed(call: ServiceCall):
        """Handle set fan speed service."""
        entity_id = call.data.get("entity_id")
        speed = call.data.get("speed")
        
        # Find the device
        for entry_id, device in hass.data[DOMAIN].items():
            # Check if this is the right device (simplified)
            # In real implementation, you'd need to map entity_id to device
            pass
    
    async def async_handle_set_swing_mode(call: ServiceCall):
        """Handle set swing mode service."""
        entity_id = call.data.get("entity_id")
        swing_mode = call.data.get("swing_mode")
        
        # Find the device
        for entry_id, device in hass.data[DOMAIN].items():
            # Check if this is the right device
            pass
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FAN_SPEED,
        async_handle_set_fan_speed,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("speed"): vol.In(["auto", "low", "medium", "high"])
        })
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SWING_MODE,
        async_handle_set_swing_mode,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("swing_mode"): vol.In(["off", "vertical"])
        })
    )