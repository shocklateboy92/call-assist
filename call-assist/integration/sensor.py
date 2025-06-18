"""Platform for Call Assist custom entities."""

import logging
from typing import Any, Dict, List

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CallAssistCoordinator
from .call_station import CallStationEntity
from .contact import CallAssistContactEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Call Assist entities from a config entry."""
    
    coordinator: CallAssistCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Wait for initial data
    await coordinator.async_config_entry_first_refresh()
    
    entities: List[SensorEntity] = []
    
    if coordinator.data:
        # Create call station entities
        for station_data in coordinator.data.get("call_stations", []):
            entities.append(CallStationEntity(coordinator, station_data))
        
        # Create contact entities  
        for contact_data in coordinator.data.get("contacts", []):
            entities.append(CallAssistContactEntity(coordinator, contact_data))
    
    if entities:
        async_add_entities(entities, update_before_add=True)
        _LOGGER.info("Added %d Call Assist entities", len(entities))
    else:
        _LOGGER.warning("No Call Assist entities found from broker")