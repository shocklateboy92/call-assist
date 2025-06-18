"""Contact entities for Call Assist."""

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import CallAssistCoordinator
from .const import (
    CONTACT_AVAILABILITY_ONLINE,
    CONTACT_AVAILABILITY_OFFLINE,
    CONTACT_AVAILABILITY_BUSY,
    CONTACT_AVAILABILITY_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


class CallAssistContactEntity(CoordinatorEntity, Entity):
    """Represents a call contact."""
    
    def __init__(self, coordinator: CallAssistCoordinator, contact_data: Dict[str, Any]):
        """Initialize the contact entity."""
        super().__init__(coordinator)
        self._contact_id = contact_data["contact_id"]
        self._display_name = contact_data["display_name"]
        self._protocol = contact_data["protocol"]
        self._address = contact_data["address"]
        self._avatar_url = contact_data.get("avatar_url")
        self._favorite = contact_data.get("favorite", False)
        
        # State from coordinator data or events
        self._availability = CONTACT_AVAILABILITY_UNKNOWN
        self._last_seen = None
        
        # Update from coordinator if available
        if coordinator.data:
            contacts = coordinator.data.get("contacts", [])
            for contact in contacts:
                if contact["contact_id"] == self._contact_id:
                    self._availability = contact["availability"]
                    break
    
    @property
    def unique_id(self) -> str:
        """Return unique ID for this entity."""
        return f"call_assist_contact_{self._contact_id}"
    
    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._display_name
    
    @property
    def state(self) -> str:
        """Return the state of the contact."""
        return self._availability
    
    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture URL."""
        return self._avatar_url
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        return {
            "contact_id": self._contact_id,
            "protocol": self._protocol,
            "address": self._address,
            "favorite": self._favorite,
            "last_seen": self._last_seen,
        }
    
    @property
    def icon(self) -> str:
        """Return the icon for this entity."""
        if self._availability == CONTACT_AVAILABILITY_ONLINE:
            return "mdi:account-voice"
        elif self._availability == CONTACT_AVAILABILITY_BUSY:
            return "mdi:account-cancel"
        elif self._availability == CONTACT_AVAILABILITY_OFFLINE:
            return "mdi:account-off"
        else:
            return "mdi:account-question"
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True  # Contact entities are always available for display
    
    async def async_added_to_hass(self) -> None:
        """Subscribe to contact status updates when added to hass."""
        await super().async_added_to_hass()
        
        # Subscribe to contact-specific updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"call_assist_contact_{self._contact_id}",
                self._handle_contact_update
            )
        )
    
    @callback
    def _handle_contact_update(self, data: Dict[str, Any]) -> None:
        """Handle contact updates from gRPC stream."""
        self._availability = data.get("availability", self._availability)
        self._last_seen = data.get("last_seen", self._last_seen)
        self.async_write_ha_state()
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return
            
        contacts = self.coordinator.data.get("contacts", [])
        for contact in contacts:
            if contact["contact_id"] == self._contact_id:
                self._availability = contact["availability"]
                break
        
        self.async_write_ha_state()
    
    @property
    def should_poll(self) -> bool:
        """No polling needed - we get push updates."""
        return False