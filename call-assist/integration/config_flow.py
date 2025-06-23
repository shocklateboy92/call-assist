"""Config flow for Call Assist integration."""

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT
from .grpc_client import CallAssistGrpcClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)

STEP_ACCOUNT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("protocol"): vol.In(["matrix", "xmpp"]),
        vol.Required("account_id"): str,
        vol.Optional("display_name"): str,
        vol.Required("homeserver"): str,
        vol.Required("access_token"): str,
        vol.Required("user_id"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    client = CallAssistGrpcClient(data[CONF_HOST], data[CONF_PORT])

    try:
        await client.async_connect()
        status = await client.async_get_status()
        await client.async_disconnect()

        return {
            "title": f"Call Assist ({data[CONF_HOST]})",
            "broker_version": status.get("version", "unknown"),
        }
    except Exception as ex:
        _LOGGER.error("Connection test failed: %s", ex)
        raise CannotConnect from ex


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class CallAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Call Assist."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    # Set domain as class attribute
    domain = DOMAIN

    def __init__(self):
        """Initialize config flow."""
        self._broker_data = {}

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - broker connection."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Set unique ID based on broker connection first, regardless of validation
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)

                # Create entry with just broker configuration
                # Accounts can be added later through services or UI
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

    async def async_step_account(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle account configuration step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Set unique ID based on broker + account combination
            unique_id = f"{self._broker_data[CONF_HOST]}:{self._broker_data[CONF_PORT]}:{user_input['protocol']}:{user_input['account_id']}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                # Test account credentials with broker
                await self._validate_account(user_input)

                # Combine broker and account data
                config_data = {
                    **self._broker_data,
                    "protocol": user_input["protocol"],
                    "account_id": user_input["account_id"],
                    "display_name": user_input.get(
                        "display_name", user_input["account_id"]
                    ),
                    "credentials": {
                        "homeserver": user_input["homeserver"],
                        "access_token": user_input["access_token"],
                        "user_id": user_input["user_id"],
                    },
                }

                title = f"Call Assist - {user_input.get('display_name', user_input['account_id'])} ({user_input['protocol'].title()})"
                return self.async_create_entry(title=title, data=config_data)

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="account",
            data_schema=STEP_ACCOUNT_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow."""
        return CallAssistOptionsFlow(config_entry)

    async def _validate_account(self, account_data: Dict[str, Any]) -> None:
        """Validate account credentials with the broker."""
        client = CallAssistGrpcClient(
            self._broker_data[CONF_HOST], self._broker_data[CONF_PORT]
        )

        try:
            await client.async_connect()

            # Test adding the account to the broker
            success = await client.add_account(
                protocol=account_data["protocol"],
                account_id=account_data["account_id"],
                display_name=account_data.get(
                    "display_name", account_data["account_id"]
                ),
                credentials={
                    "homeserver": account_data["homeserver"],
                    "access_token": account_data["access_token"],
                    "user_id": account_data["user_id"],
                },
            )

            if not success:
                raise CannotConnect("Failed to add account to broker")

        finally:
            await client.async_disconnect()


class CallAssistOptionsFlow(config_entries.OptionsFlow):
    """Handle Call Assist options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self._protocol_data = {}

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        return await self.async_step_account_dashboard(user_input)

    async def async_step_account_dashboard(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show account dashboard."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_account":
                return await self.async_step_select_protocol()

        # Simple dashboard schema for testing
        data_schema = vol.Schema(
            {vol.Optional("action"): vol.In(["add_account", "manage_accounts"])}
        )

        return self.async_show_form(
            step_id="account_dashboard",
            data_schema=data_schema,
        )

    async def async_step_select_protocol(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select protocol for new account."""
        if user_input is not None:
            # Store protocol data and move to credentials step
            self._protocol_data = user_input
            return await self.async_step_enter_credentials()

        data_schema = vol.Schema(
            {
                vol.Required("protocol"): vol.In(["matrix", "xmpp"]),
                vol.Optional("display_name"): str,
            }
        )

        return self.async_show_form(
            step_id="select_protocol",
            data_schema=data_schema,
        )

    async def async_step_enter_credentials(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter credentials for the account."""
        if user_input is not None:
            # Create account device
            from homeassistant.helpers import device_registry as dr

            device_registry = dr.async_get(self.hass)

            protocol = self._protocol_data.get("protocol", "unknown")
            display_name = self._protocol_data.get(
                "display_name", f"Account ({protocol})"
            )
            user_id = user_input.get("user_id", "unknown")

            device_registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, f"account_{protocol}_{user_id}")},
                name=f"Call Assist {protocol.title()} Account - {display_name}",
                manufacturer="Call Assist",
                model=f"{protocol.title()} Account",
                via_device=(
                    DOMAIN,
                    f"broker_{self.config_entry.data[CONF_HOST]}:{self.config_entry.data[CONF_PORT]}",
                ),
            )

            return self.async_create_entry(title="Account added", data={})

        # Simple credentials schema for testing
        data_schema = vol.Schema(
            {
                vol.Required("homeserver"): str,
                vol.Required("access_token"): str,
                vol.Required("user_id"): str,
            }
        )

        return self.async_show_form(
            step_id="enter_credentials",
            data_schema=data_schema,
        )
