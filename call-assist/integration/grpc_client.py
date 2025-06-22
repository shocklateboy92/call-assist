"""Async gRPC client for Call Assist broker."""

import asyncio
import logging
from typing import AsyncIterator, Dict, Any

import grpc
from grpc import aio as grpc_aio
from grpc.aio import AioRpcError

# Import protobuf generated files
from .proto_gen.broker_integration_pb2_grpc import BrokerIntegrationStub
from .proto_gen.broker_integration_pb2 import (
    ConfigurationRequest,
    CallRequest,
    CallResponse,
    CallTerminateRequest,
    CredentialsRequest,
)
from .proto_gen.common_pb2 import CallState, ContactPresence, CallEvent

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
        """Get current broker entities and system status."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            # Get entities from broker - this is the new primary data source
            from google.protobuf import empty_pb2
            entities_request = empty_pb2.Empty()
            entities_response = await self.stub.GetEntities(entities_request)
            
            # Get system capabilities for additional context
            capabilities_request = empty_pb2.Empty()
            capabilities_response = await self.stub.GetSystemCapabilities(capabilities_request)
            
            # Transform entities into the format the integration expects
            call_stations = []
            contacts = []
            
            for entity in entities_response.entities:
                if entity.entity_type == 1:  # ENTITY_TYPE_CALL_STATION
                    call_stations.append({
                        "station_id": entity.entity_id,
                        "name": entity.name,
                        "state": entity.state,
                        "camera_entity": entity.attributes.get("camera_entity", ""),
                        "media_player_entity": entity.attributes.get("media_player_entity", ""),
                        "protocols": entity.attributes.get("protocols", "matrix").split(","),
                        "available": entity.available,
                        "icon": entity.icon,
                        "capabilities": list(entity.capabilities),
                        "current_call_id": entity.attributes.get("current_call_id"),
                    })
                elif entity.entity_type == 2:  # ENTITY_TYPE_CONTACT
                    contacts.append({
                        "contact_id": entity.entity_id,
                        "display_name": entity.name,
                        "protocol": entity.attributes.get("protocol", "matrix"),
                        "address": entity.attributes.get("address", ""),
                        "availability": entity.state,
                        "avatar_url": entity.attributes.get("avatar_url"),
                        "favorite": entity.attributes.get("favorite", "false").lower() == "true",
                        "available": entity.available,
                        "icon": entity.icon,
                    })
            
            return {
                "version": "1.0.0",  # Static version for now
                "call_stations": call_stations,
                "contacts": contacts,
                "broker_capabilities": {
                    "video_codecs": list(capabilities_response.broker_capabilities.video_codecs),
                    "audio_codecs": list(capabilities_response.broker_capabilities.audio_codecs),
                    "webrtc_support": capabilities_response.broker_capabilities.webrtc_support,
                },
                "available_plugins": [
                    {
                        "protocol": plugin.protocol,
                        "available": plugin.available,
                        "capabilities": {
                            "video_codecs": list(plugin.capabilities.video_codecs),
                            "audio_codecs": list(plugin.capabilities.audio_codecs),
                            "webrtc_support": plugin.capabilities.webrtc_support,
                        }
                    }
                    for plugin in capabilities_response.available_plugins
                ]
            }
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to get status: %s", ex)
            raise
    
    async def stream_events(self) -> AsyncIterator[CallEvent]:
        """Stream events from broker."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            # Status call - use empty request for now
            from google.protobuf import empty_pb2
            request = empty_pb2.Empty()  # Empty request for streaming
            async for event in self.stub.StreamCallEvents(request):
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
            request = CallRequest(
                camera_entity_id=station_id,  # Assuming station_id maps to camera
                media_player_entity_id="media_player.default",  # Default media player
                target_address=address or contact_id or "",
                protocol=protocol or "matrix",
                account_id=""  # TODO: Add account selection to make_call
            )
            
            response = await self.stub.InitiateCall(request)
            return response.call_id
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to make call: %s", ex)
            raise
    
    async def end_call(self, station_id: str) -> bool:
        """End active call on a station."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = CallTerminateRequest(call_id=station_id)
            response = await self.stub.TerminateCall(request)
            return response.success
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to end call: %s", ex)
            raise
    
    async def accept_call(self, station_id: str) -> bool:
        """Accept incoming call on a station."""
        # Note: AcceptCall method may need to be implemented in the broker service
        # For now, this is a placeholder
        _LOGGER.warning("AcceptCall method not yet implemented in broker service")
        return False
    
    async def add_account(self, protocol: str, account_id: str, display_name: str, credentials: Dict[str, str]) -> bool:
        """Add a new account for a protocol."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = CredentialsRequest(
                protocol=protocol,
                account_id=account_id,
                display_name=display_name,
                credentials=credentials
            )
            
            response = await self.stub.UpdateCredentials(request)
            return response.success
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to add account: %s", ex)
            raise
    
    async def update_account(self, protocol: str, account_id: str, display_name: str, credentials: Dict[str, str]) -> bool:
        """Update an existing account."""
        # Same as add_account since UpdateCredentials handles both cases
        return await self.add_account(protocol, account_id, display_name, credentials)
    
    async def get_configured_accounts(self) -> Dict[str, Any]:
        """Get list of configured accounts from broker."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            from google.protobuf import empty_pb2
            capabilities_request = empty_pb2.Empty()
            capabilities_response = await self.stub.GetSystemCapabilities(capabilities_request)
            
            accounts = {}
            for plugin in capabilities_response.available_plugins:
                if plugin.account_id:  # Only include configured accounts
                    key = f"{plugin.protocol}_{plugin.account_id}"
                    accounts[key] = {
                        "protocol": plugin.protocol,
                        "account_id": plugin.account_id,
                        "display_name": plugin.display_name,
                        "available": plugin.available,
                        "capabilities": {
                            "video_codecs": list(plugin.capabilities.video_codecs),
                            "audio_codecs": list(plugin.capabilities.audio_codecs),
                            "webrtc_support": plugin.capabilities.webrtc_support,
                        }
                    }
            
            return accounts
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to get configured accounts: %s", ex)
            raise
    
    async def get_protocol_schemas(self) -> Dict[str, Any]:
        """Get configuration schemas for all protocols."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            from google.protobuf import empty_pb2
            request = empty_pb2.Empty()
            response = await self.stub.GetProtocolSchemas(request)
            
            schemas = {}
            for schema in response.schemas:
                credential_fields = []
                for field in schema.credential_fields:
                    credential_fields.append({
                        "key": field.key,
                        "display_name": field.display_name,
                        "description": field.description,
                        "type": field.type,
                        "required": field.required,
                        "default_value": field.default_value,
                        "allowed_values": list(field.allowed_values),
                        "sensitive": field.sensitive
                    })
                
                setting_fields = []
                for field in schema.setting_fields:
                    setting_fields.append({
                        "key": field.key,
                        "display_name": field.display_name,
                        "description": field.description,
                        "type": field.type,
                        "required": field.required,
                        "default_value": field.default_value,
                        "allowed_values": list(field.allowed_values)
                    })
                
                schemas[schema.protocol] = {
                    "protocol": schema.protocol,
                    "display_name": schema.display_name,
                    "description": schema.description,
                    "credential_fields": credential_fields,
                    "setting_fields": setting_fields,
                    "example_account_ids": list(schema.example_account_ids)
                }
            
            return schemas
            
        except AioRpcError as ex:
            _LOGGER.error("Failed to get protocol schemas: %s", ex)
            raise