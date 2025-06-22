"""Config flow for Call Assist integration."""

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT,
    CONF_ACCOUNT_ID, CONF_DISPLAY_NAME, CONF_PROTOCOL, CONF_CREDENTIALS,
    CONF_MATRIX_HOMESERVER, CONF_MATRIX_ACCESS_TOKEN, CONF_MATRIX_USER_ID,
    CONF_XMPP_USERNAME, CONF_XMPP_PASSWORD, CONF_XMPP_SERVER, CONF_XMPP_PORT
)
from .grpc_client import CallAssistGrpcClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)

STEP_ACCOUNT_PROTOCOL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROTOCOL): vol.In(["matrix", "xmpp"]),
        vol.Required(CONF_DISPLAY_NAME): str,
    }
)

STEP_MATRIX_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MATRIX_HOMESERVER, default="https://matrix.org"): str,
        vol.Required(CONF_MATRIX_ACCESS_TOKEN): str,
        vol.Required(CONF_MATRIX_USER_ID): str,
    }
)

STEP_XMPP_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_XMPP_USERNAME): str,
        vol.Required(CONF_XMPP_PASSWORD): str,
        vol.Required(CONF_XMPP_SERVER): str,
        vol.Optional(CONF_XMPP_PORT, default=5222): int,
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


class AccountConfigError(HomeAssistantError):
    """Error to indicate account configuration failed."""


class CallAssistConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Call Assist."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH
    
    # Set domain as class attribute
    domain = DOMAIN
    
    def __init__(self):
        """Initialize config flow."""
        self._account_data = {}
        self._client = None

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}
        
        if user_input is not None:
            # Set unique ID early to check for duplicates
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Store client for account management
                self._client = CallAssistGrpcClient(user_input[CONF_HOST], user_input[CONF_PORT])
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        from .dynamic_config_flow import DynamicCallAssistOptionsFlow
        return DynamicCallAssistOptionsFlow(config_entry)


class CallAssistOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Call Assist integration."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self._account_data = {}
        self._client: CallAssistGrpcClient | None = None
    
    async def async_step_init(self, user_input=None):
        """Manage account options."""
        return await self.async_step_account_menu()
    
    async def async_step_account_menu(self, user_input=None):
        """Show account management menu."""
        if self._client is None:
            self._client = CallAssistGrpcClient(
                self.config_entry.data[CONF_HOST],
                self.config_entry.data[CONF_PORT]
            )
        
        try:
            await self._client.async_connect()
            accounts = await self._client.get_configured_accounts()
            await self._client.async_disconnect()
        except Exception as ex:
            _LOGGER.error("Failed to get accounts: %s", ex)
            accounts = {}
        
        # Build menu options
        menu_options = ["add_account"]
        
        if accounts:
            for account_key in accounts.keys():
                menu_options.append(f"edit_{account_key}")
                menu_options.append(f"remove_{account_key}")
        
        # Create description text
        description = "Current accounts:\n"
        if accounts:
            for key, account in accounts.items():
                status = "✓" if account["available"] else "✗"
                description += f"\n{status} {account['display_name']} ({account['protocol']})"
        else:
            description += "No accounts configured"
        
        # For now, just show the add account form since menu support may vary
        return await self.async_step_add_account()
    
    async def async_step_add_account(self, user_input=None):
        """Add a new account."""
        errors = {}
        
        if user_input is not None:
            self._account_data.update(user_input)
            
            # Route to protocol-specific credential step
            if user_input[CONF_PROTOCOL] == "matrix":
                return await self.async_step_matrix_credentials()
            elif user_input[CONF_PROTOCOL] == "xmpp":
                return await self.async_step_xmpp_credentials()
        
        return self.async_show_form(
            step_id="add_account",
            data_schema=STEP_ACCOUNT_PROTOCOL_SCHEMA,
            errors=errors,
            description_placeholders={
                "title": "Add New Account",
                "description": "Choose the protocol and display name for your new account."
            }
        )
    
    async def async_step_matrix_credentials(self, user_input=None):
        """Configure Matrix account credentials."""
        errors = {}
        
        if user_input is not None:
            try:
                # Extract Matrix-specific credentials
                credentials = {
                    "homeserver": user_input[CONF_MATRIX_HOMESERVER],
                    "access_token": user_input[CONF_MATRIX_ACCESS_TOKEN],
                    "user_id": user_input[CONF_MATRIX_USER_ID],
                }
                
                # Add account to broker
                if self._client:
                    await self._client.async_connect()
                    success = await self._client.add_account(
                        protocol="matrix",
                        account_id=user_input[CONF_MATRIX_USER_ID],
                        display_name=self._account_data[CONF_DISPLAY_NAME],
                        credentials=credentials
                    )
                    await self._client.async_disconnect()
                else:
                    success = False
                
                if success:
                    return self.async_create_entry(
                        title="Account Added",
                        data={"account_added": True}
                    )
                else:
                    errors["base"] = "add_account_failed"
                    
            except Exception as ex:
                _LOGGER.error("Failed to add Matrix account: %s", ex)
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="matrix_credentials",
            data_schema=STEP_MATRIX_CREDENTIALS_SCHEMA,
            errors=errors,
            description_placeholders={
                "title": f"Matrix Credentials: {self._account_data.get(CONF_DISPLAY_NAME, '')}",
                "description": "Enter your Matrix account credentials. You can get an access token from Element > Settings > Help & About > Advanced."
            }
        )
    
    async def async_step_xmpp_credentials(self, user_input=None):
        """Configure XMPP account credentials."""
        errors = {}
        
        if user_input is not None:
            try:
                # Extract XMPP-specific credentials
                credentials = {
                    "username": user_input[CONF_XMPP_USERNAME],
                    "password": user_input[CONF_XMPP_PASSWORD],
                    "server": user_input[CONF_XMPP_SERVER],
                    "port": str(user_input[CONF_XMPP_PORT]),
                }
                
                # Create account ID from username@server
                account_id = f"{user_input[CONF_XMPP_USERNAME]}@{user_input[CONF_XMPP_SERVER]}"
                
                # Add account to broker
                if self._client:
                    await self._client.async_connect()
                    success = await self._client.add_account(
                        protocol="xmpp",
                        account_id=account_id,
                        display_name=self._account_data[CONF_DISPLAY_NAME],
                        credentials=credentials
                    )
                    await self._client.async_disconnect()
                else:
                    success = False
                
                if success:
                    return self.async_create_entry(
                        title="Account Added",
                        data={"account_added": True}
                    )
                else:
                    errors["base"] = "add_account_failed"
                    
            except Exception as ex:
                _LOGGER.error("Failed to add XMPP account: %s", ex)
                errors["base"] = "cannot_connect"
        
        return self.async_show_form(
            step_id="xmpp_credentials",
            data_schema=STEP_XMPP_CREDENTIALS_SCHEMA,
            errors=errors,
            description_placeholders={
                "title": f"XMPP Credentials: {self._account_data.get(CONF_DISPLAY_NAME, '')}",
                "description": "Enter your XMPP account credentials."
            }
        )