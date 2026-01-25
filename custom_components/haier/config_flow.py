"""Config flow for Haier AC integration."""
import logging
import voluptuous as vol
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_HEALTH_MODE,
    CONF_HEALTH_MODE_TYPE,
    HEALTH_MODE_TYPES,
    DEFAULT_NAME
)
from .device import test_connection

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_IP_ADDRESS): str,
    vol.Required(CONF_MAC): str,
    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
    vol.Required(CONF_HEALTH_MODE, default=False): bool,
    vol.Optional(CONF_HEALTH_MODE_TYPE, default="switch"): vol.In(HEALTH_MODE_TYPES),
})


class HaierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Haier AC."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate MAC address format
            mac = user_input[CONF_MAC].upper().replace(":", "").replace("-", "")
            if len(mac) != 12 or not all(c in "0123456789ABCDEF" for c in mac):
                errors[CONF_MAC] = "invalid_mac_format"
            else:
                # Test connection to device
                try:
                    if await self.hass.async_add_executor_job(
                        test_connection, user_input[CONF_IP_ADDRESS]
                    ):
                        # Create unique ID from MAC address
                        await self.async_set_unique_id(mac)
                        self._abort_if_unique_id_configured()
                        
                        return self.async_create_entry(
                            title=user_input[CONF_NAME],
                            data=user_input
                        )
                    else:
                        errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "ip_example": "192.168.1.100",
                "mac_example": "AA:BB:CC:DD:EE:FF"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return HaierOptionsFlowHandler(config_entry)


class HaierOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Haier AC options."""
    
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
    
    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_HEALTH_MODE,
                    default=self.config_entry.options.get(CONF_HEALTH_MODE, False)
                ): bool,
                vol.Optional(
                    CONF_HEALTH_MODE_TYPE,
                    default=self.config_entry.options.get(CONF_HEALTH_MODE_TYPE, "switch")
                ): vol.In(HEALTH_MODE_TYPES),
            })
        )