"""Config flow for Call Assist integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT, DOMAIN
from .grpc_client import CallAssistGrpcClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    import asyncio

    client = CallAssistGrpcClient(data[CONF_HOST], data[CONF_PORT])

    _LOGGER.info(
        "Testing connection to Call Assist broker at %s:%s",
        data[CONF_HOST],
        data[CONF_PORT],
    )

    try:
        # Add timeout to prevent hanging
        await asyncio.wait_for(client.async_connect(), timeout=5.0)
        response = await asyncio.wait_for(client.health_check(), timeout=5.0)
        await client.async_disconnect()

        if not response.healthy:
            raise CannotConnect(f"Broker unhealthy: {response.message}")

        return {
            "title": f"Call Assist ({data[CONF_HOST]})",
            "broker_version": "1.0.0",  # TODO: Get from health check
        }
    except Exception as ex:
        _LOGGER.error("Connection test failed: %s (type: %s)", ex, type(ex).__name__)
        raise CannotConnect from ex


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class CallAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Call Assist."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - broker connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Set unique ID based on broker connection
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
