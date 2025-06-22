"""Device triggers for Call Assist accounts."""

import logging
from typing import Any, Dict, List
import voluptuous as vol

from homeassistant.core import HomeAssistant, CALLBACK_TYPE
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Device trigger types
TRIGGER_CONNECTION_LOST = "connection_lost"
TRIGGER_CONNECTION_RESTORED = "connection_restored"
TRIGGER_ACCOUNT_ERROR = "account_error"
TRIGGER_CALL_RECEIVED = "call_received"
TRIGGER_CALL_STARTED = "call_started"

ACCOUNT_TRIGGERS = [
    TRIGGER_CONNECTION_LOST,
    TRIGGER_CONNECTION_RESTORED,
    TRIGGER_ACCOUNT_ERROR,
    TRIGGER_CALL_RECEIVED,
    TRIGGER_CALL_STARTED,
]

TRIGGER_SCHEMA = cv.TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACCOUNT_TRIGGERS),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> List[Dict[str, Any]]:
    """List device triggers for Call Assist accounts."""
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
    
    # Build available triggers
    triggers = []
    
    for trigger_type in ACCOUNT_TRIGGERS:
        triggers.append({
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        })
    
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: Dict[str, Any],
    action: Any,
    trigger_info: Dict[str, Any],
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    trigger_type = config[CONF_TYPE]
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
    
    # Set up event listener for this trigger
    event_type = f"call_assist_account_{trigger_type}"
    
    def trigger_event_listener(event):
        """Handle trigger event."""
        if event.data.get("account_id") == account_id:
            hass.async_run_hass_job(action, {
                "trigger": {
                    "platform": "device",
                    "device_id": device_id,
                    "domain": DOMAIN,
                    "type": trigger_type,
                    "account_id": account_id,
                    "protocol": protocol,
                }
            })
    
    # Register event listener
    remove_listener = hass.bus.async_listen(event_type, trigger_event_listener)
    
    return remove_listener


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: Dict[str, Any]
) -> Dict[str, vol.Schema]:
    """List trigger capabilities."""
    return {}