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
    vol.Optional("timeout", default=3000): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
})


class HaierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Haier AC."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize the config flow."""
        self._errors = {}
        self._discovered_devices = {}

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate MAC address format
            mac = user_input[CONF_MAC].upper().replace(":", "").replace("-", "")
            if len(mac) != 12 or not all(c in "0123456789ABCDEF" for c in mac):
                errors[CONF_MAC] = "invalid_mac_format"
            else:
                # Test connection to device with better error handling
                try:
                    # Use async_add_executor_job for blocking I/O
                    can_connect = await self.hass.async_add_executor_job(
                        test_connection, user_input[CONF_IP_ADDRESS]
                    )
                    
                    if can_connect:
                        # Format MAC address consistently
                        formatted_mac = ':'.join(mac[i:i+2] for i in range(0, 12, 2))
                        user_input[CONF_MAC] = formatted_mac
                        
                        # Create unique ID from MAC address
                        await self.async_set_unique_id(formatted_mac)
                        self._abort_if_unique_id_configured()
                        
                        # Store timeout in options if provided
                        timeout = user_input.pop("timeout", 3000)
                        
                        return self.async_create_entry(
                            title=user_input[CONF_NAME],
                            data=user_input,
                            options={"timeout": timeout}
                        )
                    else:
                        errors["base"] = "cannot_connect"
                        _LOGGER.warning(
                            f"Cannot connect to device at {user_input[CONF_IP_ADDRESS]}. "
                            f"Make sure the device is powered on and connected to the network."
                        )
                except Exception as ex:
                    _LOGGER.error(f"Connection test exception: {ex}")
                    errors["base"] = "cannot_connect"
        
        # Show form with errors if any
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "ip_example": "192.168.1.100",
                "mac_example": "AA:BB:CC:DD:EE:FF",
                "note": "Note: Device must be powered on and connected to your local network."
            }
        )

    async def async_step_zeroconf(self, discovery_info):
        """Handle zeroconf discovery."""
        # Implement discovery if needed in the future
        return await self.async_step_user()

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
        
        # Get current options or use defaults
        current_timeout = self.config_entry.options.get("timeout", 3000)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "timeout",
                    default=current_timeout,
                    description="Connection timeout in milliseconds"
                ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
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