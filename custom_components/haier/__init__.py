"""The Haier AC integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS, CONF_HEALTH_MODE, CONF_HEALTH_MODE_TYPE
from .device import HaierDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Haier AC from a config entry."""
    
    # Get options with defaults
    options = entry.options
    timeout = options.get("timeout", 5000)
    
    # Create device instance
    device = HaierDevice(
        hass,
        entry.data[CONF_IP_ADDRESS],
        entry.data[CONF_MAC],
        entry.data[CONF_NAME],
        entry.data.get(CONF_HEALTH_MODE, False),
        entry.data.get(CONF_HEALTH_MODE_TYPE, "switch"),
        timeout
    )
    
    try:
        # Connect to device
        await device.async_connect()
    except Exception as ex:
        _LOGGER.error(f"Failed to connect to device during setup: {ex}")
        # Don't raise ConfigEntryNotReady immediately, try to continue
        # The device might become available later
    
    # Store device in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device
    
    # Register device in device registry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device.mac)},
        manufacturer="Haier",
        name=device.name,
        model="Air Conditioner",
        sw_version="1.0",
        configuration_url=f"http://{device.ip_address}",
    )
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Setup update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    _LOGGER.info(f"Haier AC {device.name} setup completed")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        device = hass.data[DOMAIN].pop(entry.entry_id, None)
        if device:
            await device.async_disconnect()
        _LOGGER.info(f"Haier AC {entry.data[CONF_NAME]} unloaded")
    
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.info(f"Configuration updated for {entry.data[CONF_NAME]}")
    await hass.config_entries.async_reload(entry.entry_id)