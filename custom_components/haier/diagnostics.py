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
        return {"error": "Device not found in hass.data"}
    
    # Basic connection test
    connection_test = {
        "ip_address": device.ip_address,
        "port": device.port,
        "connected": device.is_connected,
        "available": device.available,
        "mac_address": device.mac,
    }
    
    # Device state
    device_state = {
        "power": device.power,
        "mode": device.mode,
        "mode_name": device.MODE_MAP.get(device.mode, "unknown"),
        "target_temperature": device.target_temperature,
        "current_temperature": device.current_temperature,
        "fan_speed": device.fan_speed,
        "fan_speed_name": device.FAN_SPEED_MAP.get(device.fan_speed, "unknown"),
        "swing_mode": device.swing_mode,
        "health_mode": device.health_mode,
    }
    
    # Config entry info
    config_info = {
        "entry_id": config_entry.entry_id,
        "title": config_entry.title,
        "data": dict(config_entry.data),
        "options": dict(config_entry.options),
        "state": config_entry.state.value if config_entry.state else None,
    }
    
    return {
        "connection": connection_test,
        "device_state": device_state,
        "config_entry": config_info,
        "diagnostic_note": "Port 56800 is used based on nmap scan results. "
                          "If connection fails, verify the device is powered on "
                          "and port 56800 is accessible from Home Assistant."
    }