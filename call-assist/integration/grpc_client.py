"""Async gRPC client for Call Assist broker."""

import asyncio
import logging
from typing import AsyncIterator, Dict, Any

import grpc
from grpc import aio as grpc_aio
from grpc.aio import AioRpcError

# Import protobuf generated files
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'addon', 'broker'))

from broker_integration_pb2_grpc import BrokerIntegrationStub
from broker_integration_pb2 import (
    IntegrationStatusRequest,
    IntegrationCallRequest,
    IntegrationCallResponse,
    IntegrationEvent,
)
from common_pb2 import CallState, ContactAvailability

_LOGGER = logging.getLogger(__name__)


class CallAssistGrpcClient:
    """Async gRPC client for communicating with Call Assist broker."""
    
    def __init__(self, host: str, port: int):
        """Initialize gRPC client."""
        self.host = host
        self.port = port
        self.target = f"{host}:{port}"
        self.channel: grpc_aio.Channel | None = None
        self.stub: BrokerIntegrationStub | None = None
        self._connected = False
        self._max_retries = 5
    
    def _get_channel_options(self) -> list:
        """Get channel options for long-lived connections."""
        return [
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 5000),
            ('grpc.keepalive_permit_without_calls', True),
            ('grpc.http2.max_pings_without_data', 0),
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_send_message_length', 100 * 1024 * 1024),     # 100MB
        ]
    
    async def async_connect(self) -> None:
        """Connect to the gRPC server."""
        if self._connected:
            return
            
        try:
            self.channel = grpc_aio.insecure_channel(
                self.target,
                options=self._get_channel_options()
            )
            
            # Wait for channel to be ready
            await asyncio.wait_for(
                self.channel.channel_ready(),
                timeout=10.0
            )
            
            self.stub = BrokerIntegrationStub(self.channel)
            self._connected = True
            
            _LOGGER.info("Connected to Call Assist broker at %s", self.target)
            
        except Exception as ex:
            _LOGGER.error("Failed to connect to broker: %s", ex)
            await self._cleanup()
            raise
    
    async def async_disconnect(self) -> None:
        """Disconnect from gRPC server."""
        await self._cleanup()
    
    async def _cleanup(self) -> None:
        """Clean up connection resources."""
        self._connected = False
        self.stub = None
        
        if self.channel:
            await self.channel.close()
            self.channel = None
    
    async def ensure_connection(self) -> bool:
        """Ensure connection is active with exponential backoff."""
        if self._connected and self.channel:
            try:
                # Test connection with a quick status call
                await asyncio.wait_for(
                    self.async_get_status(),
                    timeout=5.0
                )
                return True
            except Exception:
                self._connected = False
        
        # Reconnect with exponential backoff
        retry_count = 0
        while retry_count < self._max_retries:
            try:
                await self.async_connect()
                return True
            except Exception as ex:
                retry_count += 1
                wait_time = min(2 ** retry_count, 30)
                _LOGGER.warning(
                    "Reconnect attempt %d/%d failed: %s. Retrying in %ds",
                    retry_count, self._max_retries, ex, wait_time
                )
                await asyncio.sleep(wait_time)
        
        _LOGGER.error("Failed to reconnect after %d attempts", self._max_retries)
        return False
    
    async def async_get_status(self) -> Dict[str, Any]:
        """Get current broker status."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = IntegrationStatusRequest()
            response = await self.stub.GetStatus(request)
            
            return {
                "healthy": response.healthy,
                "version": response.version,
                "call_stations": [
                    {
                        "station_id": station.station_id,
                        "name": station.name,
                        "state": CallState.Name(station.state),
                        "current_call_id": station.current_call_id or None,
                    }
                    for station in response.call_stations
                ],
                "contacts": [
                    {
                        "contact_id": contact.contact_id,
                        "display_name": contact.display_name,
                        "protocol": contact.protocol,
                        "address": contact.address,
                        "availability": ContactAvailability.Name(contact.availability),
                    }
                    for contact in response.contacts
                ]
            }
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to get status: %s", ex)
            raise
    
    async def stream_events(self) -> AsyncIterator[IntegrationEvent]:
        """Stream events from broker."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = IntegrationStatusRequest()  # Empty request for streaming
            async for event in self.stub.StreamEvents(request):
                yield event
                
        except AioRpcError as ex:
            if ex.code() == grpc.StatusCode.UNAVAILABLE:
                _LOGGER.warning("Broker connection lost during streaming")
                self._connected = False
            else:
                _LOGGER.error("Streaming error: %s", ex)
            raise
    
    async def make_call(
        self, 
        station_id: str, 
        contact_id: str | None = None,
        protocol: str | None = None,
        address: str | None = None
    ) -> str:
        """Make a call from a station to a contact."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = IntegrationCallRequest(
                station_id=station_id,
                contact_id=contact_id or "",
                protocol=protocol or "",
                address=address or ""
            )
            
            response = await self.stub.MakeCall(request)
            return response.call_id
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to make call: %s", ex)
            raise
    
    async def end_call(self, station_id: str) -> bool:
        """End active call on a station."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = IntegrationCallRequest(station_id=station_id)
            response = await self.stub.EndCall(request)
            return response.success
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to end call: %s", ex)
            raise
    
    async def accept_call(self, station_id: str) -> bool:
        """Accept incoming call on a station."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = IntegrationCallRequest(station_id=station_id)
            response = await self.stub.AcceptCall(request)
            return response.success
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to accept call: %s", ex)
            raise