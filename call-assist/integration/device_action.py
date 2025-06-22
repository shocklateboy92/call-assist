"""Device actions for Call Assist account management."""

import logging
from typing import Any, Dict, List
import voluptuous as vol

from homeassistant.core import HomeAssistant, Context
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Device action types
ACTION_TEST_CONNECTION = "test_connection"
ACTION_DISABLE_ACCOUNT = "disable_account"
ACTION_ENABLE_ACCOUNT = "enable_account"
ACTION_REMOVE_ACCOUNT = "remove_account"
ACTION_UPDATE_CREDENTIALS = "update_credentials"

ACCOUNT_ACTIONS = [
    ACTION_TEST_CONNECTION,
    ACTION_DISABLE_ACCOUNT,
    ACTION_ENABLE_ACCOUNT,
    ACTION_REMOVE_ACCOUNT,
    ACTION_UPDATE_CREDENTIALS,
]

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required("type"): vol.In(ACCOUNT_ACTIONS),
        vol.Optional("credentials"): dict,
    }
)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> List[Dict[str, Any]]:
    """List device actions for Call Assist accounts."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    
    if not device or not any(
        identifier[0] == DOMAIN for identifier in device.identifiers
    ):
        return []
    
    # Check if this is an account device (not broker)
    is_account_device = False
    for identifier_domain, identifier in device.identifiers:
        if identifier_domain == DOMAIN and not identifier.startswith("broker_"):
            is_account_device = True
            break
    
    if not is_account_device:
        return []
    
    # Build available actions based on device state
    actions = []
    
    # Test connection action
    actions.append({
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
        "type": ACTION_TEST_CONNECTION,
        "name": "Test connection",
    })
    
    # Enable/Disable actions based on current state
    if device.disabled_by == dr.DeviceEntryDisabler.INTEGRATION:
        actions.append({
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            "type": ACTION_ENABLE_ACCOUNT,
            "name": "Enable account",
        })
    else:
        actions.append({
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            "type": ACTION_DISABLE_ACCOUNT,
            "name": "Disable account",
        })
    
    # Update credentials action
    actions.append({
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
        "type": ACTION_UPDATE_CREDENTIALS,
        "name": "Update credentials",
    })
    
    # Remove account action
    actions.append({
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
        "type": ACTION_REMOVE_ACCOUNT,
        "name": "Remove account",
    })
    
    return actions


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: Dict[str, Any],
    variables: Dict[str, Any],
    context: Context | None,
) -> None:
    """Execute a device action."""
    action_type = config["type"]
    device_id = config[CONF_DEVICE_ID]
    
    # Get device and extract account info
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    
    if not device:
        raise InvalidDeviceAutomationConfig(f"Device {device_id} not found")
    
    # Extract account identifier
    account_identifier = None
    for identifier_domain, identifier in device.identifiers:
        if identifier_domain == DOMAIN and not identifier.startswith("broker_"):
            account_identifier = identifier
            break
    
    if not account_identifier:
        raise InvalidDeviceAutomationConfig("Not a Call Assist account device")
    
    # Parse protocol and account_id from identifier
    try:
        protocol, account_id = account_identifier.split("_", 1)
    except ValueError:
        raise InvalidDeviceAutomationConfig("Invalid account identifier format")
    
    # Get coordinator from hass data
    call_assist_data = hass.data.get(DOMAIN, {})
    coordinator = None
    device_manager = None
    
    for entry_data in call_assist_data.values():
        if isinstance(entry_data, dict):
            coordinator = entry_data.get("coordinator")
            device_manager = entry_data.get("device_manager")
            break
    
    if not coordinator or not device_manager:
        raise InvalidDeviceAutomationConfig("Call Assist integration not available")
    
    # Execute the action
    try:
        if action_type == ACTION_TEST_CONNECTION:
            await _test_account_connection(coordinator, account_id)
            
        elif action_type == ACTION_DISABLE_ACCOUNT:
            await _disable_account(coordinator, device_manager, protocol, account_id, device_id)
            
        elif action_type == ACTION_ENABLE_ACCOUNT:
            await _enable_account(coordinator, device_manager, protocol, account_id, device_id)
            
        elif action_type == ACTION_REMOVE_ACCOUNT:
            await _remove_account(coordinator, device_manager, protocol, account_id)
            
        elif action_type == ACTION_UPDATE_CREDENTIALS:
            credentials = config.get("credentials", {})
            await _update_credentials(coordinator, protocol, account_id, credentials)
            
        else:
            raise InvalidDeviceAutomationConfig(f"Unknown action type: {action_type}")
            
    except Exception as ex:
        _LOGGER.error("Failed to execute device action %s: %s", action_type, ex)
        raise


async def _test_account_connection(coordinator, account_id: str) -> None:
    """Test account connection."""
    result = await coordinator.client.test_account_connection(account_id)
    
    if result.get("success"):
        _LOGGER.info("Account %s connection test successful", account_id)
    else:
        _LOGGER.warning("Account %s connection test failed: %s", 
                       account_id, result.get("error", "Unknown error"))


async def _disable_account(coordinator, device_manager, protocol: str, account_id: str, device_id: str) -> None:
    """Disable an account."""
    success = await coordinator.client.toggle_account_status(account_id, disable=True)
    
    if success:
        # Update device registry
        device_registry = dr.async_get(coordinator.hass)
        device_registry.async_update_device(
            device_id,
            disabled_by=dr.DeviceEntryDisabler.INTEGRATION
        )
        _LOGGER.info("Account %s disabled", account_id)
    else:
        _LOGGER.error("Failed to disable account %s", account_id)


async def _enable_account(coordinator, device_manager, protocol: str, account_id: str, device_id: str) -> None:
    """Enable an account."""
    success = await coordinator.client.toggle_account_status(account_id, disable=False)
    
    if success:
        # Update device registry
        device_registry = dr.async_get(coordinator.hass)
        device_registry.async_update_device(
            device_id,
            disabled_by=None
        )
        _LOGGER.info("Account %s enabled", account_id)
    else:
        _LOGGER.error("Failed to enable account %s", account_id)


async def _remove_account(coordinator, device_manager, protocol: str, account_id: str) -> None:
    """Remove an account."""
    success = await coordinator.client.remove_account(account_id)
    
    if success:
        # Remove device from registry
        await device_manager.async_remove_account_device(protocol, account_id)
        _LOGGER.info("Account %s removed", account_id)
    else:
        _LOGGER.error("Failed to remove account %s", account_id)


async def _update_credentials(coordinator, protocol: str, account_id: str, credentials: Dict[str, Any]) -> None:
    """Update account credentials."""
    if not credentials:
        _LOGGER.warning("No credentials provided for account %s", account_id)
        return
    
    # Get current account details for display name
    account = await coordinator.client.get_account_details(account_id)
    display_name = account.get("display_name", "") if account else ""
    
    success = await coordinator.client.update_account(
        protocol=protocol,
        account_id=account_id,
        display_name=display_name,
        credentials=credentials
    )
    
    if success:
        _LOGGER.info("Account %s credentials updated", account_id)
    else:
        _LOGGER.error("Failed to update credentials for account %s", account_id)


async def async_get_action_capabilities(
    hass: HomeAssistant, config: Dict[str, Any]
) -> Dict[str, vol.Schema]:
    """List action capabilities."""
    action_type = config["type"]
    
    if action_type == ACTION_UPDATE_CREDENTIALS:
        return {
            "extra_fields": vol.Schema({
                vol.Optional("credentials"): dict,
            })
        }
    
    return {}