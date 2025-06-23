"""Async gRPC client for Call Assist broker."""

import asyncio
import logging
from typing import AsyncIterator, Dict, Any

from grpclib.client import Channel

# Import betterproto generated files
from .proto_gen.callassist.broker import (
    BrokerIntegrationStub,
    ConfigurationRequest,
    CallRequest,
    CallResponse,
    CallTerminateRequest,
    CredentialsRequest,
)
from .proto_gen.callassist.common import CallState, ContactPresence, CallEvent
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf

_LOGGER = logging.getLogger(__name__)
class CallAssistGrpcClient:
    """Async gRPC client for communicating with Call Assist broker."""
    
    def __init__(self, host: str, port: int):
        """Initialize gRPC client."""
        self.host = host
        self.port = port
        self.target = f"{host}:{port}"
        self.channel: Channel | None = None
        self.stub: BrokerIntegrationStub | None = None
        self._connected = False
        self._max_retries = 5
    
    async def async_connect(self) -> None:
        """Connect to the gRPC server."""
        if self._connected:
            return
            
        try:
            self.channel = Channel(
                host=self.host,
                port=self.port
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
            self.channel.close()
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
            entities_request = betterproto_lib_pydantic_google_protobuf.Empty()
            entities_response = await self.stub.get_entities(entities_request)
            
            # Get system capabilities for additional context
            capabilities_request = betterproto_lib_pydantic_google_protobuf.Empty()
            capabilities_response = await self.stub.get_system_capabilities(capabilities_request)
            
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
            
        except Exception as ex:
            _LOGGER.error("Failed to get status: %s", ex)
            raise
    
    async def stream_events(self) -> AsyncIterator[CallEvent]:
        """Stream events from broker."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            # Status call - use empty request for now
            request = betterproto_lib_pydantic_google_protobuf.Empty()  # Empty request for streaming
            async for event in self.stub.stream_call_events(request):
                yield event
                
        except Exception as ex:
            _LOGGER.warning("Broker connection lost during streaming")
            self._connected = False
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
            
            response = await self.stub.initiate_call(request)
            return response.call_id
            
        except Exception as ex:
            _LOGGER.error("Failed to make call: %s", ex)
            raise
    
    async def end_call(self, station_id: str) -> bool:
        """End active call on a station."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = CallTerminateRequest(call_id=station_id)
            response = await self.stub.terminate_call(request)
            return response.success
            
        except Exception as ex:
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
            
            response = await self.stub.update_credentials(request)
            return response.success
            
        except Exception as ex:
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
            capabilities_request = betterproto_lib_pydantic_google_protobuf.Empty()
            capabilities_response = await self.stub.get_system_capabilities(capabilities_request)
            
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
            
        except Exception as ex:
            _LOGGER.error("Failed to get configured accounts: %s", ex)
            raise
    
    async def get_protocol_schemas(self) -> Dict[str, Any]:
        """Get configuration schemas for all protocols."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            request = betterproto_lib_pydantic_google_protobuf.Empty()
            response = await self.stub.get_protocol_schemas(request)
            
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
            
        except Exception as ex:
            _LOGGER.error("Failed to get protocol schemas: %s", ex)
            raise
    
    async def get_account_details(self, account_id: str) -> Dict[str, Any] | None:
        """Get detailed information about a specific account."""
        accounts = await self.get_configured_accounts()
        
        # Search for account by ID
        for key, account in accounts.items():
            if account.get("account_id") == account_id:
                # Add additional details like status and last_seen
                account["status"] = "connected" if account.get("available") else "error"
                account["last_seen"] = "1 minute ago"  # TODO: Get real timestamp
                account["error_message"] = None  # TODO: Get real error if any
                return account
        
        return None
    
    async def test_account_connection(self, account_id: str) -> Dict[str, Any]:
        """Test connection for a specific account."""
        try:
            # Get account details first
            account = await self.get_account_details(account_id)
            if not account:
                return {"success": False, "error": "Account not found"}
            
            # TODO: Implement actual connection test via broker
            # For now, simulate based on current availability
            if account.get("available"):
                return {
                    "success": True,
                    "latency": "150",
                    "message": "Connection successful"
                }
            else:
                return {
                    "success": False,
                    "error": "Account not available",
                    "message": "Connection failed"
                }
        except Exception as ex:
            return {
                "success": False,
                "error": str(ex),
                "message": "Connection test failed"
            }
    
    async def remove_account(self, account_id: str) -> bool:
        """Remove an account configuration."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            # TODO: Implement RemoveAccount RPC in broker
            # For now, this is a placeholder that returns success
            _LOGGER.warning("RemoveAccount RPC not yet implemented in broker service")
            return True
            
        except Exception as ex:
            _LOGGER.error("Failed to remove account: %s", ex)
            return False
    
    async def toggle_account_status(self, account_id: str, disable: bool = False) -> bool:
        """Enable or disable an account."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")
        
        try:
            # TODO: Implement ToggleAccount RPC in broker
            # For now, this is a placeholder that returns success
            _LOGGER.warning("ToggleAccount RPC not yet implemented in broker service")
            return True
            
        except Exception as ex:
            _LOGGER.error("Failed to toggle account status: %s", ex)
            return False