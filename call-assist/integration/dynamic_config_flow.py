"""Data-driven config flow for Call Assist integration."""

import logging
from typing import Any, Dict, List

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT
from .grpc_client import CallAssistGrpcClient

_LOGGER = logging.getLogger(__name__)

# Field type mapping from protobuf to voluptuous
FIELD_TYPE_MAPPING = {
    0: str,  # FIELD_TYPE_STRING
    1: str,  # FIELD_TYPE_PASSWORD (same as string, UI handles masking)
    2: int,  # FIELD_TYPE_INTEGER
    3: bool, # FIELD_TYPE_BOOLEAN
    4: str,  # FIELD_TYPE_SELECT (string with restricted values)
    5: str,  # FIELD_TYPE_URL
    6: str,  # FIELD_TYPE_EMAIL
}


def _build_voluptuous_schema(fields: List[Dict[str, Any]]) -> vol.Schema:
    """Build a voluptuous schema from field definitions."""
    schema_dict = {}
    
    for field in fields:
        field_type = FIELD_TYPE_MAPPING.get(field["type"], str)
        key = field["key"]
        
        # Handle select fields with allowed values
        if field["type"] == 4 and field.get("allowed_values"):  # FIELD_TYPE_SELECT
            field_type = vol.In(field["allowed_values"])
        
        # Build the validator
        if field["required"]:
            if field.get("default_value"):
                validator = vol.Required(key, default=field["default_value"])
            else:
                validator = vol.Required(key)
        else:
            if field.get("default_value"):
                validator = vol.Optional(key, default=field["default_value"])
            else:
                validator = vol.Optional(key)
        
        schema_dict[validator] = field_type
    
    return vol.Schema(schema_dict)


class DynamicCallAssistOptionsFlow(config_entries.OptionsFlow):
    """Data-driven options flow for Call Assist integration."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self._account_data = {}
        self._client: CallAssistGrpcClient | None = None
        self._protocol_schemas: Dict[str, Any] = {}
        self._selected_protocol: str | None = None
    
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
            
            # Load protocol schemas from broker
            self._protocol_schemas = await self._client.get_protocol_schemas()
            
            # Get configured accounts
            accounts = await self._client.get_configured_accounts()
            
            await self._client.async_disconnect()
        except Exception as ex:
            _LOGGER.error("Failed to get broker data: %s", ex)
            return self.async_abort(reason="cannot_connect")
        
        # For now, just show the add account form since menu support may vary
        return await self.async_step_select_protocol()
    
    async def async_step_select_protocol(self, user_input=None):
        """Select protocol for new account."""
        errors = {}
        if user_input is not None:
            self._selected_protocol = user_input["protocol"]
            self._account_data["display_name"] = user_input["display_name"]
            
            # Route to protocol-specific credential step
            return await self.async_step_configure_credentials()
        
        # Build protocol choices from broker schemas
        protocol_choices = {}
        for protocol, schema in self._protocol_schemas.items():
            protocol_choices[protocol] = schema["display_name"]
        
        if not protocol_choices:
            return self.async_abort(reason="no_protocols_available")
        
        schema = vol.Schema({
            vol.Required("protocol"): vol.In(protocol_choices),
            vol.Required("display_name"): str,
        })
        
        description = "Available protocols:\\n"
        for protocol, schema_info in self._protocol_schemas.items():
            description += f"\\n• **{schema_info['display_name']}**: {schema_info['description']}"
        
        return self.async_show_form(
            step_id="select_protocol",
            data_schema=schema,
            errors=errors,
            description_placeholders={"protocols": description}
        )
    
    async def async_step_configure_credentials(self, user_input=None):
        """Configure credentials for selected protocol."""
        if not self._selected_protocol:
            return self.async_abort(reason="no_protocol_selected")
        
        protocol_schema = self._protocol_schemas[self._selected_protocol]
        errors = {}
        
        if user_input is not None:
            try:
                # Extract account ID based on protocol
                account_id = self._extract_account_id(user_input, self._selected_protocol)
                
                # Add account to broker
                if self._client:
                    await self._client.async_connect()
                    success = await self._client.add_account(
                        protocol=self._selected_protocol,
                        account_id=account_id,
                        display_name=self._account_data["display_name"],
                        credentials=user_input
                    )
                    await self._client.async_disconnect()
                    
                    if success:
                        return self.async_create_entry(
                            title="Account Added",
                            data={"account_added": True}
                        )
                    else:
                        errors["base"] = "add_account_failed"
                else:
                    errors["base"] = "cannot_connect"
                    
            except Exception as ex:
                _LOGGER.error("Failed to add %s account: %s", self._selected_protocol, ex)
                errors["base"] = "cannot_connect"
        
        # Build dynamic schema from broker-provided field definitions
        schema = _build_voluptuous_schema(protocol_schema["credential_fields"])
        
        # Build help text with field descriptions
        help_text = f"Configure your {protocol_schema['display_name']} account:\\n\\n"
        for field in protocol_schema["credential_fields"]:
            help_text += f"• **{field['display_name']}**: {field['description']}\\n"
        
        if protocol_schema.get("example_account_ids"):
            help_text += f"\\nExample account IDs: {', '.join(protocol_schema['example_account_ids'])}"
        
        return self.async_show_form(
            step_id="configure_credentials",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "title": f"{protocol_schema['display_name']}: {self._account_data['display_name']}",
                "description": help_text
            }
        )
    
    def _extract_account_id(self, credentials: Dict[str, Any], protocol: str) -> str:
        """Extract account ID from credentials based on protocol."""
        if protocol == "matrix":
            return credentials.get("user_id", "")
        elif protocol == "xmpp":
            username = credentials.get("username", "")
            server = credentials.get("server", "")
            return f"{username}@{server}" if username and server else ""
        else:
            # Generic fallback - use first credential field as account ID
            protocol_schema = self._protocol_schemas.get(protocol, {})
            for field in protocol_schema.get("credential_fields", []):
                if field["key"] in credentials:
                    return credentials[field["key"]]
            return ""