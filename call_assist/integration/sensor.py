"""Sensor platform for Call Assist integration."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CallAssistCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Call Assist sensors from a config entry."""
    coordinator: CallAssistCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    # Create sensors for all broker entities
    for entity_id, entity_data in coordinator.broker_entities.items():
        entities.append(CallAssistBrokerEntity(coordinator, entity_id, entity_data))

    if entities:
        async_add_entities(entities)

    # Set up listener for new entities
    @callback
    def handle_coordinator_update() -> None:
        """Handle coordinator data updates."""
        new_entities = []
        existing_entity_ids = {entity.unique_id for entity in entities}

        for entity_id, entity_data in coordinator.broker_entities.items():
            if entity_id not in existing_entity_ids:
                new_entities.append(CallAssistBrokerEntity(coordinator, entity_id, entity_data))

        if new_entities:
            async_add_entities(new_entities)
            entities.extend(new_entities)

    # Listen for coordinator updates
    coordinator.async_add_listener(handle_coordinator_update)


class CallAssistBrokerEntity(CoordinatorEntity[CallAssistCoordinator], SensorEntity):
    """Representation of a Call Assist broker entity."""

    def __init__(
        self,
        coordinator: CallAssistCoordinator,
        entity_id: str,
        entity_data: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entity_id = entity_id
        self._entity_data = entity_data
        self._attr_unique_id = f"{DOMAIN}_{entity_id}"
        self._attr_name = entity_data["name"]
        self._attr_icon = entity_data.get("icon", "mdi:phone")

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        entity_data = self.coordinator.get_entity_data(self._entity_id)
        return entity_data["state"] if entity_data else "unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        entity_data = self.coordinator.get_entity_data(self._entity_id)
        if not entity_data:
            return {}

        attributes = dict(entity_data.get("attributes", {}))
        attributes.update({
            "entity_type": entity_data.get("type"),
            "capabilities": entity_data.get("capabilities", []),
            "last_updated": entity_data.get("last_updated"),
            "broker_entity_id": self._entity_id,
        })

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        entity_data = self.coordinator.get_entity_data(self._entity_id)
        return entity_data.get("available", False) if entity_data else False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"broker_{self.coordinator.host}:{self.coordinator.port}")},
            name="Call Assist Broker",
            manufacturer="Call Assist",
            model="Broker",
            sw_version=self.coordinator.broker_version,
        )
