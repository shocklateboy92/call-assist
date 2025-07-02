"""Data coordinator for Call Assist integration."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MONITORED_DOMAINS
from .grpc_client import CallAssistGrpcClient

_LOGGER = logging.getLogger(__name__)


class CallAssistCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator for managing Call Assist data and communications."""

    def __init__(
        self, hass: HomeAssistant, host: str, port: int, config_entry: ConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),  # Health check interval
        )

        self.host: str = host
        self.port: int = port
        self.config_entry = config_entry
        self.grpc_client = CallAssistGrpcClient(host, port)

        # Track HA entities we're monitoring
        self._tracked_cameras: set[str] = set()
        self._tracked_media_players: set[str] = set()

        # Track broker entities we've created
        self.broker_entities: dict[str, dict[str, Any]] = {}

        # Tasks for streaming
        self._broker_stream_task: asyncio.Task[None] | None = None

        # State change listener
        self._state_change_listener: Callable[[], None] | None = None

        # Connection tracking
        self._last_successful_connection: datetime | None = None
        self._broker_restart_detected = False

    async def async_setup(self) -> None:
        """Set up the coordinator."""
        # Connect to broker
        await self.grpc_client.async_connect()

        # Test connection
        response = await self.grpc_client.health_check()
        if not response.healthy:
            raise RuntimeError(f"Broker health check failed: {response.message}")

        _LOGGER.info("Connected to Call Assist broker at %s:%s", self.host, self.port)

        # Start monitoring HA entities
        await self._start_ha_monitoring()

        # Start broker entity streaming
        await self._start_broker_streaming()

        # Record successful connection
        self._last_successful_connection = datetime.now(UTC)

        _LOGGER.info("Call Assist coordinator setup complete")

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        # Cancel streaming tasks
        if self._broker_stream_task:
            self._broker_stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._broker_stream_task

        # Remove state change listener
        if self._state_change_listener:
            self._state_change_listener()
            self._state_change_listener = None

        # Disconnect from broker
        await self.grpc_client.async_disconnect()

        _LOGGER.info("Call Assist coordinator shutdown complete")

    async def _start_ha_monitoring(self) -> None:
        """Start monitoring HA entities for changes."""
        # Get all camera and media_player entities
        entity_registry = er.async_get(self.hass)

        for entity in entity_registry.entities.values():
            if entity.domain in MONITORED_DOMAINS:
                if entity.domain == "camera":
                    self._tracked_cameras.add(entity.entity_id)
                elif entity.domain == "media_player":
                    self._tracked_media_players.add(entity.entity_id)

        _LOGGER.info(
            "Monitoring %d cameras and %d media players",
            len(self._tracked_cameras),
            len(self._tracked_media_players),
        )

        # Set up state change listener
        self._state_change_listener = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._handle_state_change
        )

        # Send initial state of all entities
        await self._send_initial_entities()

        # Send the initial batch to broker
        await self._send_entity_batch()

    async def _send_initial_entities(self) -> None:
        """Send initial state of all monitored entities to broker."""
        all_entities = self._tracked_cameras | self._tracked_media_players

        for entity_id in all_entities:
            state = self.hass.states.get(entity_id)
            if state:
                await self._send_entity_update(entity_id, state)

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle state change events."""
        entity_id = event.data["entity_id"]

        # Only process entities we're tracking
        if entity_id not in (self._tracked_cameras | self._tracked_media_players):
            return

        new_state = event.data["new_state"]
        if new_state:
            # Schedule entity update and batch send
            asyncio.create_task(self._handle_entity_update(entity_id, new_state))

    async def _send_entity_update(self, entity_id: str, state: Any) -> None:
        """Send entity update to broker."""
        domain = entity_id.split(".")[0]

        # Get HA base URL - prefer external_url, fallback to internal_url
        ha_base_url = (
            self.hass.config.external_url
            or self.hass.config.internal_url
            or (
                f"http://{self.hass.config.api.host}:{self.hass.config.api.port}"
                if self.hass.config.api
                else "http://localhost:8123"
            )
        )

        # Create entity update message
        entity_update = {
            "entity_id": entity_id,
            "domain": domain,
            "name": state.attributes.get("friendly_name", entity_id),
            "state": state.state,
            "attributes": {k: str(v) for k, v in state.attributes.items()},
            "available": state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
            "last_updated": datetime.now(UTC),
            "ha_base_url": ha_base_url,
        }

        # Send to broker via stream (handled by streaming task)
        await self.grpc_client.send_ha_entity_update(entity_update)

    async def _handle_entity_update(self, entity_id: str, state: Any) -> None:
        """Handle entity update by queuing it and sending batch."""
        # Queue the entity update
        await self._send_entity_update(entity_id, state)
        # Send the batch (single entity in this case)
        await self._send_entity_batch()

    async def _send_entity_batch(self) -> None:
        """Send queued entity updates to broker as a batch."""
        await self.grpc_client.stream_ha_entities()

    async def _resend_all_entities(self) -> None:
        """Re-send all tracked entities to broker after reconnection."""
        _LOGGER.info(
            "Re-streaming %d entities to broker after reconnection",
            len(self._tracked_cameras) + len(self._tracked_media_players),
        )

        # Re-send all tracked entities
        await self._send_initial_entities()

        # Send the batch to broker
        await self._send_entity_batch()

        _LOGGER.info("Completed re-streaming entities to broker")

    async def _start_broker_streaming(self) -> None:
        """Start streaming broker entities."""
        self._broker_stream_task = asyncio.create_task(self._stream_broker_entities())

    async def _stream_broker_entities(self) -> None:
        """Stream broker entity updates."""
        try:
            async for entity_update in self.grpc_client.stream_broker_entities():
                # Store entity data
                self.broker_entities[entity_update.entity_id] = {
                    "entity_id": entity_update.entity_id,
                    "name": entity_update.name,
                    "type": entity_update.entity_type,
                    "state": entity_update.state,
                    "attributes": dict(entity_update.attributes),
                    "icon": entity_update.icon,
                    "available": entity_update.available,
                    "capabilities": list(entity_update.capabilities),
                    "last_updated": entity_update.last_updated,
                }

                # Notify listeners that data has changed
                self.async_set_updated_data(self.broker_entities)

        except Exception as ex:
            _LOGGER.warning("Broker entity streaming failed: %s", ex)
            # Clear broker entities on connection loss
            self.broker_entities.clear()
            self.async_set_updated_data(self.broker_entities)
            raise

    @property
    def broker_version(self) -> str:
        """Get broker version."""
        return getattr(self.grpc_client, "_broker_version", "unknown")

    def get_entity_data(self, entity_id: str) -> dict[str, Any] | None:
        """Get data for a specific broker entity."""
        return self.broker_entities.get(entity_id)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from broker - used by DataUpdateCoordinator for health checks."""
        try:
            # Perform health check
            response = await self.grpc_client.health_check()
            if not response.healthy:
                raise UpdateFailed(f"Broker health check failed: {response.message}")

            # Check if broker has restarted (lost entity state)
            if (
                self._last_successful_connection
                and not self._broker_restart_detected
                and (self._tracked_cameras or self._tracked_media_players)
                and not self.broker_entities
            ):
                _LOGGER.info("Broker restart detected - will re-stream all entities")
                self._broker_restart_detected = True
                # Re-stream all entities
                await self._resend_all_entities()

            # Update connection timestamp
            self._last_successful_connection = datetime.now(UTC)
            self._broker_restart_detected = False

            return self.broker_entities

        except Exception as ex:
            _LOGGER.error("Health check failed: %s", ex)
            # Reset connection flag in grpc_client
            self.grpc_client._connected = False
            raise UpdateFailed(f"Failed to connect to broker: {ex}") from ex
