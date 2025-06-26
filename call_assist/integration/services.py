"""Services for Call Assist integration."""

import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import CallAssistCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_START_CALL = "start_call"

START_CALL_SCHEMA = vol.Schema({
    vol.Required("call_station_id"): cv.string,
    vol.Required("contact"): cv.string,
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Call Assist."""
    
    async def async_start_call(call: ServiceCall) -> ServiceResponse:
        """Start a call using the specified call station and contact."""
        call_station_id = call.data["call_station_id"]
        contact = call.data["contact"]
        
        _LOGGER.info("Starting call from %s to %s", call_station_id, contact)
        
        # Find the coordinator for this call station
        coordinator = None
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            coord = entry_data.get("coordinator")
            if coord and isinstance(coord, CallAssistCoordinator):
                # Check if this coordinator has the call station
                if call_station_id in coord.broker_entities:
                    coordinator = coord
                    break
        
        if not coordinator:
            raise ServiceValidationError(
                f"Call station '{call_station_id}' not found in any Call Assist integration"
            )
        
        try:
            # Call the broker to start the call
            response = await coordinator.grpc_client.start_call(call_station_id, contact)
            
            if response.success:
                _LOGGER.info("Call started successfully: %s", response.message)
                return {
                    "success": True,
                    "message": response.message,
                    "call_id": response.call_id,
                }
            else:
                _LOGGER.error("Call failed to start: %s", response.message)
                raise ServiceValidationError(f"Call failed to start: {response.message}")
                
        except Exception as ex:
            _LOGGER.error("Error starting call: %s", ex)
            raise ServiceValidationError(f"Error starting call: {ex}") from ex
    
    # Register the service
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_CALL,
        async_start_call,
        schema=START_CALL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    
    _LOGGER.info("Call Assist services registered")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services for Call Assist."""
    hass.services.async_remove(DOMAIN, SERVICE_START_CALL)
    _LOGGER.info("Call Assist services unloaded")