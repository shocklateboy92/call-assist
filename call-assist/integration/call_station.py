"""Call station entities for Call Assist."""

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import CallAssistCoordinator
from .const import (
    CALL_STATE_IDLE,
    CALL_STATE_RINGING,
    CALL_STATE_IN_CALL,
    CALL_STATE_UNAVAILABLE,
)

_LOGGER = logging.getLogger(__name__)


class CallStationEntity(CoordinatorEntity, Entity):
    """Represents a call station (camera + media player combo)."""

    def __init__(
        self, coordinator: CallAssistCoordinator, station_config: Dict[str, Any]
    ):
        """Initialize the call station entity."""
        super().__init__(coordinator)
        self._station_id = station_config["station_id"]
        self._name = station_config["name"]
        self._camera_entity = station_config["camera_entity"]
        self._media_player_entity = station_config["media_player_entity"]
        self._protocols = station_config.get("protocols", ["matrix"])

        # State from coordinator data or events
        self._state = CALL_STATE_IDLE
        self._current_call_id = None
        self._current_contact_id = None

        # Update from coordinator if available
        if coordinator.data:
            stations = coordinator.data.get("call_stations", [])
            for station in stations:
                if station["station_id"] == self._station_id:
                    self._state = station["state"]
                    self._current_call_id = station.get("current_call_id")
                    break

    @property
    def unique_id(self) -> str:
        """Return unique ID for this entity."""
        return f"call_assist_station_{self._station_id}"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the call station."""
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        return {
            "station_id": self._station_id,
            "camera_entity": self._camera_entity,
            "media_player_entity": self._media_player_entity,
            "protocols": self._protocols,
            "current_call_id": self._current_call_id,
            "current_contact_id": self._current_contact_id,
        }

    @property
    def icon(self) -> str:
        """Return the icon for this entity."""
        if self._state == CALL_STATE_IN_CALL:
            return "mdi:video"
        elif self._state == CALL_STATE_RINGING:
            return "mdi:phone-ring"
        elif self._state == CALL_STATE_UNAVAILABLE:
            return "mdi:video-off"
        else:
            return "mdi:video-account"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._state != CALL_STATE_UNAVAILABLE

    async def async_added_to_hass(self) -> None:
        """Subscribe to gRPC events when added to hass."""
        await super().async_added_to_hass()

        # Subscribe to station-specific updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"call_assist_station_{self._station_id}",
                self._handle_station_update,
            )
        )

    @callback
    def _handle_station_update(self, data: Dict[str, Any]) -> None:
        """Handle station updates from gRPC stream."""
        self._state = data.get("state", self._state)
        self._current_call_id = data.get("call_id")
        self._current_contact_id = data.get("contact_id")
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        stations = self.coordinator.data.get("call_stations", [])
        for station in stations:
            if station["station_id"] == self._station_id:
                self._state = station["state"]
                self._current_call_id = station.get("current_call_id")
                break

        self.async_write_ha_state()

    @property
    def should_poll(self) -> bool:
        """No polling needed - we get push updates."""
        return False
