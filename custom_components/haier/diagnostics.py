"""Diagnostics support for Haier AC."""
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    device = hass.data[DOMAIN].get(config_entry.entry_id)
    
    if not device:
        return {"error": "Device not found"}
    
    return {
        "device_info": {
            "name": device.name,
            "ip_address": device.ip_address,
            "mac": device.mac,
            "available": device.available,
            "connected": device._connected,
            "last_update": device._last_update.isoformat() if device._last_update else None,
        },
        "state": {
            "power": device.power,
            "mode": device.mode,
            "target_temperature": device.target_temperature,
            "current_temperature": device.current_temperature,
            "fan_speed": device.fan_speed,
            "swing_mode": device.swing_mode,
            "health_mode": device.health_mode,
        },
        "config_entry": {
            "data": dict(config_entry.data),
            "options": dict(config_entry.options),
        }
    }