"""Climate entity for Haier AC."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    DOMAIN,
    HAIER_MODE_COOL,
    HAIER_MODE_DRY,
    HAIER_MODE_FAN,
    HAIER_MODE_HEAT,
    HAIER_MODE_SMART,
)
from .device import DeviceNotAvailable, HaierDevice

_LOGGER = logging.getLogger(__name__)

HA_TO_HAIER_MODE: dict[HVACMode, int] = {
    HVACMode.AUTO: HAIER_MODE_SMART,
    HVACMode.COOL: HAIER_MODE_COOL,
    HVACMode.HEAT: HAIER_MODE_HEAT,
    HVACMode.FAN_ONLY: HAIER_MODE_FAN,
    HVACMode.DRY: HAIER_MODE_DRY,
}
HAIER_TO_HA_MODE: dict[int, HVACMode] = {v: k for k, v in HA_TO_HAIER_MODE.items()}

MIN_TEMP: float = 16.0
MAX_TEMP: float = 30.0
TEMP_STEP: float = 1.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    device: HaierDevice = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaierClimate(device, entry)])


class HaierClimate(ClimateEntity):
    """Representation of a Haier AC unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_hvac_modes = list(HA_TO_HAIER_MODE.keys()) + [HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, device: HaierDevice, entry: ConfigEntry) -> None:
        self._device = device
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature: float | None = None
        self._attr_current_temperature: float | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Haier AC"),
            manufacturer="Haier",
            model="AC",
        )
        mac = entry.data.get(CONF_MAC)
        if mac:
            self._attr_device_info["connections"] = {("mac", mac)}

    async def async_added_to_hass(self) -> None:
        self._device.add_listener(self._handle_state_update)

    async def async_will_remove_from_hass(self) -> None:
        self._device.remove_listener(self._handle_state_update)

    @callback
    def _handle_state_update(self, state: dict[str, Any]) -> None:
        mode = state.get("mode")
        if isinstance(mode, int) and mode in HAIER_TO_HA_MODE:
            self._attr_hvac_mode = (
                HAIER_TO_HA_MODE[mode] if state.get("power") else HVACMode.OFF
            )
        temp = state.get("temperature")
        if temp is not None:
            self._attr_target_temperature = float(temp)
            self._attr_current_temperature = float(temp)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode, rejecting unsupported modes loudly instead of silently ignoring."""
        if hvac_mode == HVACMode.OFF:
            packet = self._device.protocol.create_set_state_packet(power=False)
        else:
            haier_mode = HA_TO_HAIER_MODE.get(hvac_mode)
            if haier_mode is None:
                _LOGGER.error("Unsupported HVAC mode requested: %s", hvac_mode)
                raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")
            packet = self._device.protocol.create_set_state_packet(
                power=True, mode=haier_mode
            )

        try:
            response = await self._device.async_send_command(packet)
        except DeviceNotAvailable as exc:
            _LOGGER.warning("Cannot send HVAC mode to device: %s", exc)
            return
        if response is None:
            _LOGGER.warning(
                "No response from device after setting HVAC mode to %s", hvac_mode
            )
            return
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        packet = self._device.protocol.create_set_state_packet(
            power=True, temperature=float(temperature)
        )
        try:
            response = await self._device.async_send_command(packet)
        except DeviceNotAvailable as exc:
            _LOGGER.warning("Cannot send temperature to device: %s", exc)
            return
        if response is None:
            _LOGGER.warning(
                "No response from device after setting temperature to %s", temperature
            )
            return
        self._attr_target_temperature = float(temperature)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)