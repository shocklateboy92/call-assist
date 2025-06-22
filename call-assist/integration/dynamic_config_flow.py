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
        self._selected_account_id: str | None = None
    
    async def async_step_init(self, user_input=None):
        """Manage account options."""
        return await self.async_step_account_dashboard()
    
    async def async_step_account_dashboard(self, user_input=None):
        """Show account management dashboard."""
        if self._client is None:
            self._client = CallAssistGrpcClient(
                self.config_entry.data[CONF_HOST],
                self.config_entry.data[CONF_PORT]
            )
        
        try:
            await self._client.async_connect()
            
            # Load protocol schemas and accounts
            self._protocol_schemas = await self._client.get_protocol_schemas()
            accounts_dict = await self._client.get_configured_accounts()
            # Convert dict to list for UI
            accounts = list(accounts_dict.values())
            
            await self._client.async_disconnect()
        except Exception as ex:
            _LOGGER.error("Failed to get broker data: %s", ex)
            return self.async_abort(reason="cannot_connect")
        
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_account":
                return await self.async_step_select_protocol()
            elif action.startswith("manage_"):
                self._selected_account_id = action.replace("manage_", "")
                return await self.async_step_manage_account()
            elif action.startswith("test_"):
                self._selected_account_id = action.replace("test_", "")
                return await self.async_step_test_account()
            elif action.startswith("remove_"):
                self._selected_account_id = action.replace("remove_", "")
                return await self.async_step_confirm_remove_account()
        
        # Build account dashboard
        return self._build_account_dashboard(accounts)
    
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
                        # Trigger device registry update for new account
                        await self._refresh_devices_after_account_change()
                        
                        return self.async_create_entry(
                            title="Account Added",
                            data={"account_added": True}
                        )
                    else:
                        errors["base"] = "add_account_failed"
                        _LOGGER.error(f"Account addition failed for {self._selected_protocol} account {account_id}")
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
    
    async def _refresh_devices_after_account_change(self) -> None:
        """Refresh device registry after account changes."""
        try:
            # Get device manager from hass data
            from .const import DOMAIN
            call_assist_data = self.hass.data.get(DOMAIN, {})
            
            for entry_data in call_assist_data.values():
                if isinstance(entry_data, dict) and "device_manager" in entry_data:
                    device_manager = entry_data["device_manager"]
                    await device_manager.async_refresh_devices()
                    break
                    
        except Exception as ex:
            _LOGGER.warning("Failed to refresh devices after account change: %s", ex)
    
    def _build_account_dashboard(self, accounts: List[Dict[str, Any]]):
        """Build the account management dashboard."""
        schema_dict = {}
        
        # Add "Add Account" option
        actions = {"add_account": "➕ Add New Account"}
        
        # Add account management options
        account_info = "**Configured Accounts:**\n\n"
        if not accounts:
            account_info += "*No accounts configured yet*\n\n"
        else:
            for account in accounts:
                status_icon = self._get_status_icon(account.get("status", "unknown"))
                display_name = account.get("display_name", account.get("account_id", "Unknown"))
                protocol = account.get("protocol", "").title()
                last_seen = account.get("last_seen", "Never")
                
                account_info += f"**{display_name}** ({protocol}) {status_icon}\n"
                account_info += f"  ID: `{account.get('account_id', 'N/A')}`\n"
                account_info += f"  Last seen: {last_seen}\n\n"
                
                # Add action options for this account
                account_id = account.get("account_id", "")
                if account_id:
                    actions[f"manage_{account_id}"] = f"⚙️ Manage {display_name}"
                    actions[f"test_{account_id}"] = f"🔍 Test {display_name}"
                    actions[f"remove_{account_id}"] = f"🗑️ Remove {display_name}"
        
        schema_dict[vol.Required("action")] = vol.In(actions)
        
        return self.async_show_form(
            step_id="account_dashboard",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "accounts": account_info,
                "title": "Call Assist Account Management"
            }
        )
    
    def _get_status_icon(self, status: str) -> str:
        """Get status icon for account status."""
        status_icons = {
            "connected": "✅",
            "connecting": "🔄", 
            "error": "❌",
            "disabled": "⏸️",
            "unknown": "❓"
        }
        return status_icons.get(status.lower(), "❓")
    
    async def async_step_manage_account(self, user_input=None):
        """Manage a specific account."""
        if not self._selected_account_id:
            return self.async_abort(reason="no_account_selected")
        
        if user_input is not None:
            action = user_input.get("action")
            if action == "back":
                return await self.async_step_account_dashboard()
            elif action == "edit_credentials":
                return await self.async_step_edit_account_credentials()
            elif action == "disable_account":
                return await self.async_step_toggle_account_status(disable=True)
            elif action == "enable_account":
                return await self.async_step_toggle_account_status(disable=False)
        
        # Get account details
        try:
            if self._client:
                await self._client.async_connect()
                account = await self._client.get_account_details(self._selected_account_id)
                await self._client.async_disconnect()
            else:
                return self.async_abort(reason="cannot_connect")
        except Exception as ex:
            _LOGGER.error("Failed to get account details: %s", ex)
            return self.async_abort(reason="cannot_connect")
        
        if not account:
            return self.async_abort(reason="account_not_found")
        
        # Build management options
        actions = {
            "edit_credentials": "🔑 Edit Credentials",
            "back": "← Back to Dashboard"
        }
        
        if account.get("status") == "disabled":
            actions["enable_account"] = "▶️ Enable Account"
        else:
            actions["disable_account"] = "⏸️ Disable Account"
        
        account_info = f"""
**Account Details:**

• **Display Name:** {account.get('display_name', 'N/A')}
• **Protocol:** {account.get('protocol', 'N/A').title()}
• **Account ID:** `{account.get('account_id', 'N/A')}`
• **Status:** {self._get_status_icon(account.get('status', 'unknown'))} {account.get('status', 'Unknown').title()}
• **Last Seen:** {account.get('last_seen', 'Never')}
"""
        
        if account.get("error_message"):
            account_info += f"• **Error:** {account.get('error_message')}\n"
        
        return self.async_show_form(
            step_id="manage_account",
            data_schema=vol.Schema({vol.Required("action"): vol.In(actions)}),
            description_placeholders={
                "account_info": account_info,
                "title": f"Manage Account: {account.get('display_name', 'Unknown')}"
            }
        )
    
    async def async_step_test_account(self, user_input=None):
        """Test account connection."""
        if not self._selected_account_id:
            return self.async_abort(reason="no_account_selected")
        
        # Handle retry action
        if user_input is not None and user_input.get("action") == "retry":
            # Fall through to test again
            pass
        elif user_input is not None and user_input.get("action") == "back":
            return await self.async_step_account_dashboard()
        
        try:
            if self._client:
                await self._client.async_connect()
                result = await self._client.test_account_connection(self._selected_account_id)
                await self._client.async_disconnect()
            else:
                return self.async_abort(reason="cannot_connect")
        except Exception as ex:
            _LOGGER.error("Failed to test account: %s", ex)
            result = {"success": False, "error": str(ex)}
        
        if result.get("success"):
            message = f"✅ Connection test successful!\n\nLatency: {result.get('latency', 'N/A')}ms"
        else:
            message = f"❌ Connection test failed!\n\nError: {result.get('error', 'Unknown error')}"
        
        return self.async_show_form(
            step_id="test_result",
            data_schema=vol.Schema({
                vol.Required("action", default="back"): vol.In({
                    "back": "← Back to Dashboard",
                    "retry": "🔄 Test Again"
                })
            }),
            description_placeholders={
                "result": message,
                "title": "Connection Test Result"
            }
        )
    
    async def async_step_confirm_remove_account(self, user_input=None):
        """Confirm account removal."""
        if not self._selected_account_id:
            return self.async_abort(reason="no_account_selected")
        
        if user_input is not None:
            if user_input.get("confirm") == "yes":
                try:
                    if self._client:
                        await self._client.async_connect()
                        success = await self._client.remove_account(self._selected_account_id)
                        await self._client.async_disconnect()
                        
                        if success:
                            return self.async_create_entry(
                                title="Account Removed",
                                data={"account_removed": True}
                            )
                        else:
                            return self.async_abort(reason="remove_account_failed")
                    else:
                        return self.async_abort(reason="cannot_connect")
                except Exception as ex:
                    _LOGGER.error("Failed to remove account: %s", ex)
                    return self.async_abort(reason="cannot_connect")
            else:
                return await self.async_step_account_dashboard()
        
        return self.async_show_form(
            step_id="confirm_remove_account",
            data_schema=vol.Schema({
                vol.Required("confirm"): vol.In({
                    "no": "❌ Cancel",
                    "yes": "🗑️ Yes, Remove Account"
                })
            }),
            description_placeholders={
                "warning": f"⚠️ **Warning:** This will permanently remove the account and all associated data.\n\nAccount ID: `{self._selected_account_id}`",
                "title": "Confirm Account Removal"
            }
        )
    
    async def async_step_toggle_account_status(self, user_input=None, disable=False):
        """Toggle account enabled/disabled status."""
        if not self._selected_account_id:
            return self.async_abort(reason="no_account_selected")
        
        try:
            if self._client:
                await self._client.async_connect()
                success = await self._client.toggle_account_status(
                    self._selected_account_id, 
                    disable=disable
                )
                await self._client.async_disconnect()
                
                if success:
                    action = "disabled" if disable else "enabled"
                    return self.async_create_entry(
                        title=f"Account {action.title()}",
                        data={"account_toggled": True, "action": action}
                    )
                else:
                    return self.async_abort(reason="toggle_account_failed")
            else:
                return self.async_abort(reason="cannot_connect")
        except Exception as ex:
            _LOGGER.error("Failed to toggle account status: %s", ex)
            return self.async_abort(reason="cannot_connect")
    
    async def async_step_test_result(self, user_input=None):
        """Handle test result actions."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "back":
                return await self.async_step_account_dashboard()
            elif action == "retry":
                return await self.async_step_test_account()
        
        # This should not be reached, but handle gracefully
        return await self.async_step_account_dashboard()
    
    async def async_step_edit_account_credentials(self, user_input=None):
        """Edit account credentials."""
        if not self._selected_account_id:
            return self.async_abort(reason="no_account_selected")
        
        # Get current account details
        try:
            if self._client:
                await self._client.async_connect()
                account = await self._client.get_account_details(self._selected_account_id)
                await self._client.async_disconnect()
            else:
                return self.async_abort(reason="cannot_connect")
        except Exception as ex:
            _LOGGER.error("Failed to get account details: %s", ex)
            return self.async_abort(reason="cannot_connect")
        
        if not account:
            return self.async_abort(reason="account_not_found")
        
        # Get protocol schema for editing
        protocol = account.get("protocol")
        if not protocol or protocol not in self._protocol_schemas:
            return self.async_abort(reason="protocol_not_supported")
        
        protocol_schema = self._protocol_schemas[protocol]
        errors = {}
        
        if user_input is not None:
            try:
                # Update account credentials
                if self._client:
                    await self._client.async_connect()
                    success = await self._client.update_account(
                        protocol=protocol,
                        account_id=self._selected_account_id,
                        display_name=account.get("display_name", ""),
                        credentials=user_input
                    )
                    await self._client.async_disconnect()
                    
                    if success:
                        return self.async_create_entry(
                            title="Credentials Updated",
                            data={"credentials_updated": True}
                        )
                    else:
                        errors["base"] = "update_credentials_failed"
                else:
                    errors["base"] = "cannot_connect"
                    
            except Exception as ex:
                _LOGGER.error("Failed to update credentials: %s", ex)
                errors["base"] = "cannot_connect"
        
        # Build credential edit form
        schema = _build_voluptuous_schema(protocol_schema["credential_fields"])
        
        help_text = f"Update credentials for **{account.get('display_name', 'Unknown')}**:\\n\\n"
        for field in protocol_schema["credential_fields"]:
            help_text += f"• **{field['display_name']}**: {field['description']}\\n"
        
        return self.async_show_form(
            step_id="edit_account_credentials",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "title": f"Edit Credentials: {account.get('display_name', 'Unknown')}",
                "description": help_text
            }
        )