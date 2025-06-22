"""Coordinator for Call Assist gRPC streaming."""

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

import grpc
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .grpc_client import CallAssistGrpcClient
from .const import DOMAIN, EVENT_CALL_ASSIST_CALL_EVENT, EVENT_CALL_ASSIST_CONTACT_EVENT

_LOGGER = logging.getLogger(__name__)


class CallAssistCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Coordinator for Call Assist gRPC streaming."""
    
    def __init__(self, hass: HomeAssistant, host: str, port: int):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),  # Fallback polling
        )
        self.client = CallAssistGrpcClient(host, port)
        self._streaming_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._device_manager = None  # Will be set by device manager after creation
        
    async def async_setup(self) -> None:
        """Setup coordinator and start streaming."""
        try:
            await self.client.async_connect()
            await self.async_refresh()
            
            # Start background streaming
            self._streaming_task = self.hass.async_create_task(
                self._handle_streaming(), eager_start=True
            )
            
        except Exception as ex:
            _LOGGER.error("Failed to setup coordinator: %s", ex)
            raise
    
    async def _handle_streaming(self) -> None:
        """Handle streaming gRPC events."""
        try:
            async for event in self.client.stream_events():
                if self._shutdown_event.is_set():
                    break
                    
                await self._process_event(event)
                
        except grpc.RpcError as ex:
            _LOGGER.error("gRPC streaming error: %s", ex)
            # Coordinator will handle reconnection via update_interval
            
    async def _process_event(self, event) -> None:
        """Process incoming gRPC event."""
        event_type = event.WhichOneof("event")
        
        if event_type == "call_event":
            await self._handle_call_event(event.call_event)
        elif event_type == "contact_status_event":
            await self._handle_contact_status(event.contact_status_event)
        elif event_type == "system_event":
            await self._handle_system_event(event.system_event)
    
    async def _handle_call_event(self, call_event) -> None:
        """Handle call state changes."""
        station_id = call_event.station_id
        
        # Update call station state
        async_dispatcher_send(
            self.hass,
            f"call_assist_station_{station_id}",
            {
                "state": call_event.state,
                "call_id": call_event.call_id,
                "contact_id": call_event.contact_id,
            }
        )
        
        # Fire HA event for automations
        self.hass.bus.async_fire(
            EVENT_CALL_ASSIST_CALL_EVENT,
            {
                "station_id": station_id,
                "call_id": call_event.call_id,
                "state": call_event.state,
                "contact_id": call_event.contact_id,
            }
        )
    
    async def _handle_contact_status(self, contact_event) -> None:
        """Handle contact availability changes."""
        async_dispatcher_send(
            self.hass,
            f"call_assist_contact_{contact_event.contact_id}",
            {
                "availability": contact_event.availability,
                "last_seen": contact_event.last_seen,
            }
        )
        
        # Fire HA event for automations
        self.hass.bus.async_fire(
            EVENT_CALL_ASSIST_CONTACT_EVENT,
            {
                "contact_id": contact_event.contact_id,
                "availability": contact_event.availability,
                "last_seen": contact_event.last_seen,
            }
        )
    
    async def _handle_system_event(self, system_event) -> None:
        """Handle system events."""
        _LOGGER.info("System event: %s", system_event.message)
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data by fetching status and pushing accounts on reconnection."""
        try:
            # Ensure connection and push accounts if we have a device manager
            if self._device_manager:
                await self._device_manager.async_push_accounts_to_broker_on_reconnect()
            
            return await self.client.async_get_status()
        except Exception as ex:
            _LOGGER.error("Failed to fetch status: %s", ex)
            raise
    
    def set_device_manager(self, device_manager) -> None:
        """Set the device manager reference for pushing accounts on reconnection."""
        self._device_manager = device_manager

    async def async_shutdown(self) -> None:
        """Shutdown coordinator gracefully."""
        self._shutdown_event.set()
        
        if self._streaming_task:
            try:
                await asyncio.wait_for(self._streaming_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._streaming_task.cancel()
                try:
                    await self._streaming_task
                except asyncio.CancelledError:
                    pass
        
        await self.client.async_disconnect()
    
    # Service methods
    async def make_call(
        self, 
        station_id: str, 
        contact_id: str | None = None,
        protocol: str | None = None,
        address: str | None = None
    ) -> str:
        """Make a call through the broker."""
        return await self.client.make_call(station_id, contact_id, protocol, address)
    
    async def end_call(self, station_id: str) -> bool:
        """End a call through the broker."""
        return await self.client.end_call(station_id)
    
    async def accept_call(self, station_id: str) -> bool:
        """Accept a call through the broker."""
        return await self.client.accept_call(station_id)