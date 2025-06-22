"""Service implementations for Call Assist."""

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .coordinator import CallAssistCoordinator
from .const import (
    DOMAIN,
    SERVICE_MAKE_CALL,
    SERVICE_END_CALL,
    SERVICE_ACCEPT_CALL,
    SERVICE_ADD_CONTACT,
    SERVICE_REMOVE_CONTACT,
    SERVICE_ADD_ACCOUNT,
    SERVICE_REMOVE_ACCOUNT,
    SERVICE_UPDATE_ACCOUNT,
    CONF_PROTOCOL,
    CONF_ACCOUNT_ID,
    CONF_DISPLAY_NAME,
    CONF_CREDENTIALS,
)

_LOGGER = logging.getLogger(__name__)

# Service schemas
MAKE_CALL_SCHEMA = vol.Schema(
    {
        vol.Required("station_entity_id"): cv.entity_id,
        vol.Exclusive("contact_id", "target"): str,
        vol.Exclusive("address", "target"): str,
        vol.Optional("protocol"): str,
    }
)

END_CALL_SCHEMA = vol.Schema(
    {
        vol.Required("station_entity_id"): cv.entity_id,
    }
)

ACCEPT_CALL_SCHEMA = vol.Schema(
    {
        vol.Required("station_entity_id"): cv.entity_id,
    }
)

ADD_CONTACT_SCHEMA = vol.Schema(
    {
        vol.Required("contact_id"): str,
        vol.Required("display_name"): str,
        vol.Required("protocol"): str,
        vol.Required("address"): str,
        vol.Optional("avatar_url"): str,
        vol.Optional("favorite", default=False): bool,
    }
)

REMOVE_CONTACT_SCHEMA = vol.Schema(
    {
        vol.Required("contact_id"): str,
    }
)

ADD_ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROTOCOL): vol.In(["matrix", "xmpp"]),
        vol.Required(CONF_ACCOUNT_ID): str,
        vol.Required(CONF_DISPLAY_NAME): str,
        vol.Required(CONF_CREDENTIALS): dict,
    }
)

UPDATE_ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROTOCOL): vol.In(["matrix", "xmpp"]),
        vol.Required(CONF_ACCOUNT_ID): str,
        vol.Required(CONF_DISPLAY_NAME): str,
        vol.Required(CONF_CREDENTIALS): dict,
    }
)

REMOVE_ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROTOCOL): vol.In(["matrix", "xmpp"]),
        vol.Required(CONF_ACCOUNT_ID): str,
    }
)


def _get_station_id_from_entity_id(entity_id: str) -> str:
    """Extract station ID from entity ID."""
    # Convert call_assist.living_room_station -> living_room
    if entity_id.startswith("call_assist."):
        entity_name = entity_id.replace("call_assist.", "")
        if entity_name.endswith("_station"):
            return entity_name.replace("_station", "")
        elif entity_name.startswith("station_"):
            return entity_name.replace("station_", "")
    return entity_name


def _get_coordinator_for_service(hass: HomeAssistant) -> CallAssistCoordinator:
    """Get the first available coordinator."""
    if DOMAIN not in hass.data:
        raise ValueError("Call Assist integration not found")
    
    coordinators = list(hass.data[DOMAIN].values())
    if not coordinators:
        raise ValueError("No Call Assist coordinators found")
    
    return coordinators[0]  # For now, use the first coordinator


async def async_make_call(call: ServiceCall) -> None:
    """Handle make_call service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    station_entity_id = call.data["station_entity_id"]
    station_id = _get_station_id_from_entity_id(station_entity_id)
    
    contact_id = call.data.get("contact_id")
    address = call.data.get("address")
    protocol = call.data.get("protocol")
    
    try:
        call_id = await coordinator.make_call(
            station_id=station_id,
            contact_id=contact_id,
            protocol=protocol,
            address=address
        )
        _LOGGER.info("Started call %s on station %s", call_id, station_id)
        
    except Exception as ex:
        _LOGGER.error("Failed to make call: %s", ex)
        raise


async def async_end_call(call: ServiceCall) -> None:
    """Handle end_call service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    station_entity_id = call.data["station_entity_id"]
    station_id = _get_station_id_from_entity_id(station_entity_id)
    
    try:
        success = await coordinator.end_call(station_id)
        if success:
            _LOGGER.info("Ended call on station %s", station_id)
        else:
            _LOGGER.warning("Failed to end call on station %s", station_id)
            
    except Exception as ex:
        _LOGGER.error("Failed to end call: %s", ex)
        raise


async def async_accept_call(call: ServiceCall) -> None:
    """Handle accept_call service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    station_entity_id = call.data["station_entity_id"]
    station_id = _get_station_id_from_entity_id(station_entity_id)
    
    try:
        success = await coordinator.accept_call(station_id)
        if success:
            _LOGGER.info("Accepted call on station %s", station_id)
        else:
            _LOGGER.warning("Failed to accept call on station %s", station_id)
            
    except Exception as ex:
        _LOGGER.error("Failed to accept call: %s", ex)
        raise


async def async_add_contact(call: ServiceCall) -> None:
    """Handle add_contact service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    # For now, store contacts in integration data
    # TODO: Implement proper contact storage and sync with broker
    contact_data = {
        "contact_id": call.data["contact_id"],
        "display_name": call.data["display_name"],
        "protocol": call.data["protocol"],
        "address": call.data["address"],
        "avatar_url": call.data.get("avatar_url"),
        "favorite": call.data["favorite"],
    }
    
    _LOGGER.info("Adding contact: %s", contact_data["contact_id"])
    # TODO: Send to broker and create entity
    

async def async_remove_contact(call: ServiceCall) -> None:
    """Handle remove_contact service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    contact_id = call.data["contact_id"]
    
    _LOGGER.info("Removing contact: %s", contact_id)
    # TODO: Remove from broker and remove entity


async def async_add_account(call: ServiceCall) -> None:
    """Handle add_account service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    protocol = call.data[CONF_PROTOCOL]
    account_id = call.data[CONF_ACCOUNT_ID]
    display_name = call.data[CONF_DISPLAY_NAME]
    credentials = call.data[CONF_CREDENTIALS]
    
    try:
        success = await coordinator.client.add_account(
            protocol=protocol,
            account_id=account_id,
            display_name=display_name,
            credentials=credentials
        )
        
        if success:
            _LOGGER.info("Added account: %s (%s)", display_name, protocol)
            # Trigger coordinator refresh to update entities
            await coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to add account: %s (%s)", display_name, protocol)
            
    except Exception as ex:
        _LOGGER.error("Failed to add account %s (%s): %s", display_name, protocol, ex)
        raise


async def async_update_account(call: ServiceCall) -> None:
    """Handle update_account service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    protocol = call.data[CONF_PROTOCOL]
    account_id = call.data[CONF_ACCOUNT_ID]
    display_name = call.data[CONF_DISPLAY_NAME]
    credentials = call.data[CONF_CREDENTIALS]
    
    try:
        success = await coordinator.client.update_account(
            protocol=protocol,
            account_id=account_id,
            display_name=display_name,
            credentials=credentials
        )
        
        if success:
            _LOGGER.info("Updated account: %s (%s)", display_name, protocol)
            # Trigger coordinator refresh to update entities
            await coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to update account: %s (%s)", display_name, protocol)
            
    except Exception as ex:
        _LOGGER.error("Failed to update account %s (%s): %s", display_name, protocol, ex)
        raise


async def async_remove_account(call: ServiceCall) -> None:
    """Handle remove_account service."""
    hass = call.hass
    coordinator = _get_coordinator_for_service(hass)
    
    protocol = call.data[CONF_PROTOCOL]
    account_id = call.data[CONF_ACCOUNT_ID]
    
    try:
        # TODO: Implement account removal in broker
        _LOGGER.info("Removing account: %s (%s)", account_id, protocol)
        _LOGGER.warning("Account removal not yet implemented in broker")
        
    except Exception as ex:
        _LOGGER.error("Failed to remove account %s (%s): %s", account_id, protocol, ex)
        raise


async def async_setup_services(hass: HomeAssistant, coordinator: CallAssistCoordinator) -> None:
    """Set up services for Call Assist."""
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_MAKE_CALL,
        async_make_call,
        schema=MAKE_CALL_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_END_CALL,
        async_end_call,
        schema=END_CALL_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACCEPT_CALL,
        async_accept_call,
        schema=ACCEPT_CALL_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CONTACT,
        async_add_contact,
        schema=ADD_CONTACT_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_CONTACT,
        async_remove_contact,
        schema=REMOVE_CONTACT_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_ACCOUNT,
        async_add_account,
        schema=ADD_ACCOUNT_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_ACCOUNT,
        async_update_account,
        schema=UPDATE_ACCOUNT_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_ACCOUNT,
        async_remove_account,
        schema=REMOVE_ACCOUNT_SCHEMA,
    )
    
    _LOGGER.info("Call Assist services registered")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services for Call Assist."""
    
    services = [
        SERVICE_MAKE_CALL,
        SERVICE_END_CALL,
        SERVICE_ACCEPT_CALL,
        SERVICE_ADD_CONTACT,
        SERVICE_REMOVE_CONTACT,
        SERVICE_ADD_ACCOUNT,
        SERVICE_UPDATE_ACCOUNT,
        SERVICE_REMOVE_ACCOUNT,
    ]
    
    for service in services:
        hass.services.async_remove(DOMAIN, service)
    
    _LOGGER.info("Call Assist services unloaded")