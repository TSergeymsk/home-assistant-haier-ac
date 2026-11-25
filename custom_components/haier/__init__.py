"""Haier AC integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN
from .device import HaierDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    device = HaierDevice(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    if not await device.async_connect():
        # HA will retry later; do NOT create entities we cannot talk to.
        raise ConfigEntryNotReady(
            f"Cannot connect to Haier device at {entry.data[CONF_HOST]}"
        )

    await device.start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        device: HaierDevice = hass.data[DOMAIN].pop(entry.entry_id)
        await device.stop()
    return unloaded