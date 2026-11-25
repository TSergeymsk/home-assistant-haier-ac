"""Config flow for the Haier AC integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT: float = 5.0


class CannotConnect(Exception):
    """Cannot reach the device during config flow."""


class HaierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Haier AC."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._test_connection(
                    user_input[CONF_HOST], user_input[CONF_PORT]
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    user_input.get(CONF_MAC) or user_input[CONF_HOST]
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_MAC): str,
                }
            ),
            errors=errors,
        )

    async def _test_connection(self, host: str, port: int) -> None:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=CONNECT_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise CannotConnect(str(exc)) from exc
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass