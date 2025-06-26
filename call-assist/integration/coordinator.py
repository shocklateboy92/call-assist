"""Data coordinator for Call Assist integration."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Set

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    ATTR_ENTITY_ID,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

from .const import DOMAIN, MONITORED_DOMAINS
from .grpc_client import CallAssistGrpcClient

_LOGGER = logging.getLogger(__name__)


class CallAssistCoordinator(DataUpdateCoordinator):
    """Coordinator for managing Call Assist data and communications."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, config_entry):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # We use event streams, not polling
        )
        
        self.host = host
        self.port = port
        self.config_entry = config_entry
        self.grpc_client = CallAssistGrpcClient(host, port)
        
        # Track HA entities we're monitoring
        self._tracked_cameras: Set[str] = set()
        self._tracked_media_players: Set[str] = set()
        
        # Track broker entities we've created
        self.broker_entities: Dict[str, Dict[str, Any]] = {}
        
        # Track registered services
        self.registered_services: Set[str] = set()
        
        # Tasks for streaming
        self._ha_stream_task: asyncio.Task | None = None
        self._broker_stream_task: asyncio.Task | None = None
        
        # State change listener
        self._state_change_listener = None

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
        
        # Discover and register dynamic services
        await self._discover_and_register_services()
        
        _LOGGER.info("Call Assist coordinator setup complete")

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        # Cancel streaming tasks
        if self._ha_stream_task:
            self._ha_stream_task.cancel()
            try:
                await self._ha_stream_task
            except asyncio.CancelledError:
                pass
                
        if self._broker_stream_task:
            self._broker_stream_task.cancel()
            try:
                await self._broker_stream_task
            except asyncio.CancelledError:
                pass
        
        # Unregister services
        await self._unregister_services()
        
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
            len(self._tracked_media_players)
        )
        
        # Set up state change listener
        self._state_change_listener = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._handle_state_change
        )
        
        # Send initial state of all entities
        await self._send_initial_entities()
        
        # Start streaming task
        self._ha_stream_task = asyncio.create_task(self._stream_ha_entities())

    async def _send_initial_entities(self) -> None:
        """Send initial state of all monitored entities to broker."""
        all_entities = self._tracked_cameras | self._tracked_media_players
        
        for entity_id in all_entities:
            state = self.hass.states.get(entity_id)
            if state:
                await self._send_entity_update(entity_id, state)

    @callback
    def _handle_state_change(self, event) -> None:
        """Handle state change events."""
        entity_id = event.data.get(ATTR_ENTITY_ID)
        
        # Only process entities we're tracking
        if entity_id not in (self._tracked_cameras | self._tracked_media_players):
            return
            
        new_state = event.data.get("new_state")
        if new_state:
            # Schedule entity update
            asyncio.create_task(self._send_entity_update(entity_id, new_state))

    async def _send_entity_update(self, entity_id: str, state) -> None:
        """Send entity update to broker."""
        try:
            domain = entity_id.split(".")[0]
            
            # Create entity update message
            entity_update = {
                "entity_id": entity_id,
                "domain": domain,
                "name": state.attributes.get("friendly_name", entity_id),
                "state": state.state,
                "attributes": dict(state.attributes),
                "available": state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
                "last_updated": datetime.now(timezone.utc),
            }
            
            # Send to broker via stream (handled by streaming task)
            await self.grpc_client.send_ha_entity_update(entity_update)
            
        except Exception as ex:
            _LOGGER.warning("Failed to send entity update for %s: %s", entity_id, ex)

    async def _stream_ha_entities(self) -> None:
        """Stream HA entity updates to broker."""
        try:
            await self.grpc_client.stream_ha_entities()
        except Exception as ex:
            _LOGGER.error("HA entity streaming failed: %s", ex)
            # Try to reconnect
            if await self.grpc_client.ensure_connection():
                # Restart streaming
                await asyncio.sleep(1)
                await self._stream_ha_entities()

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
            _LOGGER.error("Broker entity streaming failed: %s", ex)
            # Try to reconnect
            if await self.grpc_client.ensure_connection():
                # Restart streaming
                await asyncio.sleep(1)
                await self._stream_broker_entities()

    async def _discover_and_register_services(self) -> None:
        """Discover services from broker and register them as Home Assistant services."""
        try:
            _LOGGER.info("Discovering services from broker...")
            
            service_count = 0
            async for service_def in self.grpc_client.get_service_definitions():
                await self._register_ha_service(service_def)
                service_count += 1
                _LOGGER.debug("Registered service: %s", service_def.service_name)
            
            _LOGGER.info("Service discovery complete. Registered %d services", service_count)
            
        except Exception as ex:
            _LOGGER.error("Failed to discover services: %s", ex)
            # Don't fail setup, just continue without dynamic services

    async def _register_ha_service(self, service_def) -> None:
        """Register a broker service as a Home Assistant service."""
        from homeassistant.helpers import service
        from homeassistant.core import ServiceCall
        import voluptuous as vol
        
        # Build service schema from broker service definition
        schema = {}
        for field in service_def.fields:
            if field.field_type.name == "STRING":
                field_schema = str
            elif field.field_type.name == "INTEGER":
                field_schema = int
            elif field.field_type.name == "BOOLEAN":
                field_schema = bool
            elif field.field_type.name == "SELECT":
                # Create a selector with allowed values
                field_schema = vol.In(field.options)
            else:
                field_schema = str  # Default to string
            
            if field.required:
                schema[vol.Required(field.key, description=field.description)] = field_schema
            else:
                default = field.default_value if field.default_value else None
                schema[vol.Optional(field.key, default=default, description=field.description)] = field_schema
        
        # Create service handler
        async def service_handler(call: ServiceCall) -> None:
            """Handle service call by forwarding to broker."""
            try:
                _LOGGER.info("Executing service %s with data: %s", service_def.service_name, call.data)
                
                # Convert parameters to strings (as expected by broker)
                parameters = {k: str(v) for k, v in call.data.items()}
                
                # Execute service on broker
                response = await self.grpc_client.execute_service(
                    service_def.service_name,
                    parameters,
                    f"ha_{self.config_entry.entry_id}"
                )
                
                if response.success:
                    _LOGGER.info("Service %s executed successfully: %s", 
                                service_def.service_name, response.message)
                else:
                    _LOGGER.error("Service %s failed: %s", 
                                 service_def.service_name, response.message)
                
            except Exception as ex:
                _LOGGER.error("Error executing service %s: %s", service_def.service_name, ex)
        
        # Register the service with Home Assistant
        self.hass.services.async_register(
            DOMAIN,
            service_def.service_name,
            service_handler,
            schema=vol.Schema(schema) if schema else None
        )
        
        # Track the service
        self.registered_services.add(service_def.service_name)
        
        _LOGGER.info("Registered HA service: %s.%s", DOMAIN, service_def.service_name)

    async def _unregister_services(self) -> None:
        """Unregister all dynamic services."""
        try:
            _LOGGER.info("Unregistering services...")
            
            for service_name in self.registered_services:
                self.hass.services.async_remove(DOMAIN, service_name)
                _LOGGER.info("Unregistered service: %s", service_name)
                
            # Clear registered services
            self.registered_services.clear()
            
            _LOGGER.info("Service unregistration complete")
            
        except Exception as ex:
            _LOGGER.error("Failed to unregister services: %s", ex)

    @property
    def broker_version(self) -> str:
        """Get broker version."""
        return getattr(self.grpc_client, "_broker_version", "unknown")

    def get_entity_data(self, entity_id: str) -> Dict[str, Any] | None:
        """Get data for a specific broker entity."""
        return self.broker_entities.get(entity_id)