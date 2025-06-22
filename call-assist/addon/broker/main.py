#!/usr/bin/env python3

import asyncio
import logging
import grpc
import grpc.aio
from concurrent import futures
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from proto_gen.broker_integration_pb2_grpc import BrokerIntegrationServicer, add_BrokerIntegrationServicer_to_server
from proto_gen.call_plugin_pb2_grpc import CallPluginServicer
import proto_gen.broker_integration_pb2 as bi_pb2
import proto_gen.call_plugin_pb2 as cp_pb2  
import proto_gen.common_pb2 as common_pb2
from plugin_manager import PluginManager, PluginConfiguration, PluginState

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BrokerConfiguration:
    """Broker configuration state"""
    camera_entities: Dict[str, str]
    media_player_entities: Dict[str, str] 
    enabled_protocols: List[str]

@dataclass
class AccountCredentials:
    """Credentials for a specific account on a protocol"""
    protocol: str
    account_id: str  # e.g., "user@matrix.org"
    display_name: str  # e.g., "Personal Matrix"
    credentials: Dict[str, str]
    is_valid: bool = True
    last_updated: Optional[str] = None  # ISO timestamp
    
    @property
    def unique_key(self) -> str:
        """Generate unique key for this account"""
        return f"{self.protocol}_{hash(self.account_id)}"

@dataclass
class CallInfo:
    """Information about an active call"""
    call_id: str
    camera_entity_id: str
    media_player_entity_id: str
    target_address: str
    protocol: str
    account_id: str  # Which account is used for this call
    state: 'common_pb2.CallState.ValueType'  # common_pb2.CallState enum value
    preferred_capabilities: Optional['common_pb2.MediaCapabilities'] = None

class CallAssistBroker(BrokerIntegrationServicer, CallPluginServicer):
    """
    Main broker service that implements both BrokerIntegration (for HA) 
    and CallPlugin (for managing plugins) services.
    """
    
    def __init__(self):
        self.configuration: Optional[BrokerConfiguration] = None
        self.account_credentials: Dict[str, AccountCredentials] = {}  # account_key -> credentials
        self.active_calls: Dict[str, CallInfo] = {}  # call_id -> call_info
        self.call_counter = 0
        self.plugin_manager = PluginManager()
        
        # Contact management
        self.contacts: Dict[str, 'common_pb2.Contact'] = {}  # contact_id -> Contact
        
        # Active event listeners - plugins can register callbacks here
        self.event_listeners: List = []  # For future extensibility
        
    async def UpdateConfiguration(self, request: bi_pb2.ConfigurationRequest, context) -> bi_pb2.ConfigurationResponse:
        """Update system configuration from Home Assistant"""
        try:
            logger.info(f"Updating configuration: {len(request.camera_entities)} cameras, {len(request.media_player_entities)} media players")
            
            self.configuration = BrokerConfiguration(
                camera_entities=dict(request.camera_entities),
                media_player_entities=dict(request.media_player_entities),
                enabled_protocols=list(request.enabled_protocols)
            )
            
            return bi_pb2.ConfigurationResponse(success=True, message="Configuration updated successfully")
            
        except Exception as e:
            logger.error(f"Configuration update failed: {e}")
            return bi_pb2.ConfigurationResponse(success=False, message=str(e))
    
    async def UpdateCredentials(self, request: bi_pb2.CredentialsRequest, context) -> bi_pb2.CredentialsResponse:
        """Update credentials for a specific account"""
        try:
            logger.info(f"Updating credentials for account: {request.account_id} ({request.protocol})")
            logger.info(f"Received credentials: {list(request.credentials.keys())}")
            
            account_creds = AccountCredentials(
                protocol=request.protocol,
                account_id=request.account_id,
                display_name=request.display_name,
                credentials=dict(request.credentials),
                last_updated=datetime.now().isoformat()
            )
            
            self.account_credentials[account_creds.unique_key] = account_creds
            
            # Send credentials to the relevant plugin instance
            success = await self._notify_plugin_credentials(account_creds)
            
            if success:
                return bi_pb2.CredentialsResponse(success=True, message=f"Credentials updated for {request.account_id} ({request.protocol})")
            else:
                return bi_pb2.CredentialsResponse(success=False, message=f"Plugin initialization failed for {request.account_id} ({request.protocol})")
            
        except Exception as e:
            logger.error(f"Credentials update failed for {request.account_id} ({request.protocol}): {e}")
            return bi_pb2.CredentialsResponse(success=False, message=str(e))
    
    async def InitiateCall(self, request: bi_pb2.CallRequest, context) -> bi_pb2.CallResponse:
        """Initiate a new call"""
        try:
            # Validate protocol exists
            if request.protocol not in self.plugin_manager.plugins:
                return bi_pb2.CallResponse(
                    success=False, 
                    call_id="", 
                    message=f"Unknown protocol: {request.protocol}"
                )
            
            self.call_counter += 1
            call_id = f"call_{self.call_counter}"
            
            logger.info(f"Initiating call {call_id}: {request.protocol} to {request.target_address}")
            
            # Store call information
            call_info = CallInfo(
                call_id=call_id,
                camera_entity_id=request.camera_entity_id,
                media_player_entity_id=request.media_player_entity_id,
                target_address=request.target_address,
                protocol=request.protocol,
                account_id=request.account_id,  # Store which account to use
                state=common_pb2.CallState.CALL_STATE_INITIATING,
                preferred_capabilities=request.preferred_capabilities
            )
            
            self.active_calls[call_id] = call_info
            
            # Forward to appropriate plugin
            await self._forward_call_to_plugin(call_info)
            
            return bi_pb2.CallResponse(
                success=True,
                call_id=call_id,
                message=f"Call {call_id} initiated",
                initial_state=common_pb2.CallState.CALL_STATE_INITIATING
            )
            
        except Exception as e:
            logger.error(f"Call initiation failed: {e}")
            return bi_pb2.CallResponse(success=False, call_id="", message=str(e))
    
    async def TerminateCall(self, request: bi_pb2.CallTerminateRequest, context) -> bi_pb2.CallTerminateResponse:
        """Terminate an active call"""
        try:
            call_id = request.call_id
            logger.info(f"Terminating call {call_id}")
            
            if call_id not in self.active_calls:
                return bi_pb2.CallTerminateResponse(success=False, message=f"Call {call_id} not found")
            
            call_info = self.active_calls[call_id]
            
            # TODO: Forward termination to plugin
            await self._terminate_call_on_plugin(call_info)
            
            # Remove from active calls
            del self.active_calls[call_id]
            
            return bi_pb2.CallTerminateResponse(success=True, message=f"Call {call_id} terminated")
            
        except Exception as e:
            logger.error(f"Call termination failed: {e}")
            return bi_pb2.CallTerminateResponse(success=False, message=str(e))
    
    async def StreamCallEvents(self, request, context):
        """Stream current call events and close"""
        logger.info("Sending current call events")
        
        try:
            # Send current active calls
            for call_id, call_info in self.active_calls.items():
                call_event = common_pb2.CallEvent(
                    type=common_pb2.CallEventType.CALL_EVENT_INITIATED,
                    call_id=call_id,
                    state=call_info.state,
                    metadata={"status": f"Call {call_id} active"}
                )
                yield call_event
            
            logger.info("Call events sent, closing stream")
                    
        except Exception as e:
            logger.error(f"Call event streaming failed: {e}")
    
    async def StreamContactUpdates(self, request, context):
        """Stream current contacts and close"""
        logger.info("Sending current contacts")
        
        try:
            # Send current contact list
            for contact in self.contacts.values():
                contact_update = common_pb2.ContactUpdate(
                    type=common_pb2.ContactUpdateType.CONTACT_UPDATE_INITIAL_LIST,
                    contact=contact
                )
                yield contact_update
            
            logger.info("Contact updates sent, closing stream")
                    
        except Exception as e:
            logger.error(f"Contact update streaming failed: {e}")
    
    async def StreamHealthStatus(self, request, context):
        """Stream current health status and close"""
        logger.info("Sending current health status")
        
        try:
            # Send current health status
            health = common_pb2.HealthStatus(
                healthy=True,
                component="broker",
                message="Broker running normally"
            )
            yield health
            
            logger.info("Health status sent, closing stream")
                    
        except Exception as e:
            logger.error(f"Health status streaming failed: {e}")
    
    async def GetEntities(self, request, context) -> bi_pb2.EntitiesResponse:
        """Get all entities that should be exposed to Home Assistant"""
        try:
            entities = []
            
            # Create call station entities based on configuration
            if self.configuration:
                for camera_entity_id, camera_name in self.configuration.camera_entities.items():
                    for media_player_id, media_player_name in self.configuration.media_player_entities.items():
                        station_id = f"station_{camera_entity_id}_{media_player_id}".replace(".", "_")
                        
                        # Determine if this station has active calls
                        active_call = None
                        current_state = "idle"
                        for call_id, call_info in self.active_calls.items():
                            if (call_info.camera_entity_id == camera_entity_id and 
                                call_info.media_player_entity_id == media_player_id):
                                active_call = call_info
                                current_state = self._call_state_to_entity_state(call_info.state)
                                break
                        
                        # Create call station entity
                        station_entity = bi_pb2.EntityDefinition(
                            entity_id=station_id,
                            name=f"{camera_name} + {media_player_name}",
                            entity_type=bi_pb2.EntityType.ENTITY_TYPE_CALL_STATION,
                            state=current_state,
                            attributes={
                                "camera_entity": camera_entity_id,
                                "media_player_entity": media_player_id,
                                "protocols": ",".join(self.configuration.enabled_protocols),
                                "current_call_id": active_call.call_id if active_call else "",
                            },
                            icon=self._get_station_icon(current_state),
                            available=True,
                            capabilities=["make_call", "end_call"]
                        )
                        entities.append(station_entity)
            
            # Create contact entities from discovered contacts
            for contact_id, contact in self.contacts.items():
                contact_entity = bi_pb2.EntityDefinition(
                    entity_id=contact_id,
                    name=contact.display_name,
                    entity_type=bi_pb2.EntityType.ENTITY_TYPE_CONTACT,
                    state=self._presence_to_availability(contact.presence),
                    attributes={
                        "protocol": contact.protocol,
                        "address": contact.id,  # The contact.id is the protocol-specific address
                        "avatar_url": contact.avatar_url or "",
                        "favorite": "false",  # TODO: Implement favorites
                    },
                    icon=self._get_contact_icon(contact.presence),
                    available=True,
                    capabilities=["call"]
                )
                entities.append(contact_entity)
            
            # Create plugin status entities
            for protocol in self.plugin_manager.get_available_protocols():
                plugin_state = self.plugin_manager.get_plugin_state(protocol)
                configured_accounts = self.get_configured_accounts(protocol)
                is_configured = len(configured_accounts) > 0
                
                status_entity = bi_pb2.EntityDefinition(
                    entity_id=f"plugin_{protocol}",
                    name=f"{protocol.title()} Plugin",
                    entity_type=bi_pb2.EntityType.ENTITY_TYPE_PLUGIN_STATUS,
                    state=self._plugin_state_to_entity_state(plugin_state, is_configured),
                    attributes={
                        "protocol": protocol,
                        "configured": str(is_configured).lower(),
                        "state": str(plugin_state) if plugin_state else "unknown",
                    },
                    icon=self._get_plugin_icon(plugin_state, is_configured),
                    available=True,
                    capabilities=[]
                )
                entities.append(status_entity)
            
            # Create broker status entity
            broker_entity = bi_pb2.EntityDefinition(
                entity_id="broker_status",
                name="Call Assist Broker",
                entity_type=bi_pb2.EntityType.ENTITY_TYPE_BROKER_STATUS,
                state="online",
                attributes={
                    "active_calls": str(len(self.active_calls)),
                    "configured_cameras": str(len(self.configuration.camera_entities)) if self.configuration else "0",
                    "configured_players": str(len(self.configuration.media_player_entities)) if self.configuration else "0",
                    "available_protocols": ",".join(self.plugin_manager.get_available_protocols()),
                    "configured_accounts": str(len(self.account_credentials)),
                    "active_instances": str(len(self.plugin_manager.plugins)),
                },
                icon="mdi:video-switch",
                available=True,
                capabilities=[]
            )
            entities.append(broker_entity)
            
            logger.info(f"Returning {len(entities)} entities to Home Assistant")
            return bi_pb2.EntitiesResponse(entities=entities)
            
        except Exception as e:
            logger.error(f"Entity query failed: {e}")
            return bi_pb2.EntitiesResponse(entities=[])
    
    def _call_state_to_entity_state(self, call_state: 'common_pb2.CallState.ValueType') -> str:
        """Convert protobuf CallState to entity state string"""
        if call_state == common_pb2.CallState.CALL_STATE_ACTIVE:
            return "in_call"
        elif call_state in [common_pb2.CallState.CALL_STATE_INITIATING, common_pb2.CallState.CALL_STATE_RINGING]:
            return "ringing"
        elif call_state == common_pb2.CallState.CALL_STATE_FAILED:
            return "unavailable"
        else:
            return "idle"
    
    def _presence_to_availability(self, presence: 'common_pb2.ContactPresence.ValueType') -> str:
        """Convert protobuf ContactPresence to availability string"""
        if presence == common_pb2.ContactPresence.PRESENCE_ONLINE:
            return "online"
        elif presence == common_pb2.ContactPresence.PRESENCE_BUSY:
            return "busy"
        elif presence == common_pb2.ContactPresence.PRESENCE_AWAY:
            return "away"
        else:
            return "offline"
    
    def _plugin_state_to_entity_state(self, plugin_state: Optional[PluginState], is_configured: bool) -> str:
        """Convert plugin state to entity state string"""
        if not is_configured:
            return "not_configured"
        elif plugin_state == PluginState.RUNNING:
            return "connected"
        elif plugin_state == PluginState.ERROR:
            return "error"
        elif plugin_state == PluginState.STARTING:
            return "starting"
        elif plugin_state == PluginState.STOPPING:
            return "stopping"
        else:
            return "disconnected"
    
    def _get_station_icon(self, state: str) -> str:
        """Get icon for call station based on state"""
        if state == "in_call":
            return "mdi:video"
        elif state == "ringing":
            return "mdi:phone-ring"
        elif state == "unavailable":
            return "mdi:video-off"
        else:
            return "mdi:video-account"
    
    def _get_contact_icon(self, presence: 'common_pb2.ContactPresence.ValueType') -> str:
        """Get icon for contact based on presence"""
        if presence == common_pb2.ContactPresence.PRESENCE_ONLINE:
            return "mdi:account-voice"
        elif presence == common_pb2.ContactPresence.PRESENCE_BUSY:
            return "mdi:account-cancel"
        elif presence == common_pb2.ContactPresence.PRESENCE_OFFLINE:
            return "mdi:account-off"
        else:
            return "mdi:account-question"
    
    def _get_plugin_icon(self, plugin_state: Optional[PluginState], is_configured: bool) -> str:
        """Get icon for plugin based on state"""
        if not is_configured:
            return "mdi:cog-outline"
        elif plugin_state == PluginState.RUNNING:
            return "mdi:connection"
        elif plugin_state == PluginState.ERROR:
            return "mdi:alert-circle"
        else:
            return "mdi:lan-disconnect"

    async def GetSystemCapabilities(self, request, context) -> bi_pb2.SystemCapabilities:
        """Get current system capabilities"""
        try:
            # Basic broker capabilities
            broker_caps = common_pb2.MediaCapabilities(
                video_codecs=["H264", "VP8"],
                audio_codecs=["OPUS", "G711"],
                supported_resolutions=[common_pb2.Resolution(width=1920, height=1080, framerate=30)],
                webrtc_support=True
            )
            
            # Query plugin capabilities
            plugin_caps = []
            available_protocols = self.plugin_manager.get_available_protocols()
            
            for protocol in available_protocols:
                plugin_metadata = self.plugin_manager.get_plugin_info(protocol)
                plugin_state = self.plugin_manager.get_plugin_state(protocol)
                
                # Convert plugin metadata capabilities to protobuf
                caps = plugin_metadata.capabilities if plugin_metadata else None
                if caps:
                    # Plugin capabilities already have ResolutionConfig objects, convert to protobuf
                    resolutions = [
                        common_pb2.Resolution(
                            width=res.width, 
                            height=res.height, 
                            framerate=res.framerate
                        ) 
                        for res in caps.supported_resolutions
                    ]
                    
                    plugin_media_caps = common_pb2.MediaCapabilities(
                        video_codecs=caps.video_codecs,
                        audio_codecs=caps.audio_codecs,
                        supported_resolutions=resolutions,
                        webrtc_support=caps.webrtc_support
                    )
                else:
                    # Default fallback resolution
                    plugin_media_caps = common_pb2.MediaCapabilities(
                        video_codecs=[],
                        audio_codecs=[],
                        supported_resolutions=[common_pb2.Resolution(width=1280, height=720, framerate=30)],
                        webrtc_support=False
                    )
                
                # Create capabilities for each configured account
                configured_accounts = self.get_configured_accounts(protocol)
                if configured_accounts:
                    for account_creds in configured_accounts:
                        plugin_caps.append(bi_pb2.PluginCapabilities(
                            protocol=protocol,
                            account_id=account_creds.account_id,
                            display_name=account_creds.display_name,
                            available=(account_creds.is_valid and 
                                     plugin_state is not None and plugin_state != PluginState.ERROR),
                            capabilities=plugin_media_caps
                        ))
                else:
                    # No accounts configured, show protocol as unavailable
                    plugin_caps.append(bi_pb2.PluginCapabilities(
                        protocol=protocol,
                        account_id="",
                        display_name=f"{protocol.title()} (Not Configured)",
                        available=False,
                        capabilities=plugin_media_caps
                    ))
            
            return bi_pb2.SystemCapabilities(
                broker_capabilities=broker_caps,
                available_plugins=plugin_caps
            )
            
        except Exception as e:
            logger.error(f"Capability query failed: {e}")
            return bi_pb2.SystemCapabilities()
    
    async def GetProtocolSchemas(self, request, context) -> bi_pb2.ProtocolSchemasResponse:
        """Get configuration schemas for all available protocols"""
        try:
            schemas = []
            
            for protocol in self.plugin_manager.get_available_protocols():
                plugin_metadata = self.plugin_manager.get_plugin_info(protocol)
                if not plugin_metadata:
                    continue
                
                # Generate schema from plugin metadata
                schema = self._generate_protocol_schema(protocol, plugin_metadata)
                schemas.append(schema)
            
            return bi_pb2.ProtocolSchemasResponse(schemas=schemas)
            
        except Exception as e:
            logger.error(f"Protocol schema query failed: {e}")
            return bi_pb2.ProtocolSchemasResponse(schemas=[])
    
    def _generate_protocol_schema(self, protocol: str, metadata) -> bi_pb2.ProtocolSchema:
        """Generate protocol schema from plugin metadata"""
        # Protocol-specific schema definitions
        schema_definitions = {
            "matrix": {
                "display_name": "Matrix",
                "description": "Matrix is an open standard for interoperable, decentralised, real-time communication.",
                "credential_fields": [
                    {
                        "key": "homeserver",
                        "display_name": "Homeserver URL",
                        "description": "The Matrix homeserver URL (e.g., https://matrix.org)",
                        "type": bi_pb2.FieldType.FIELD_TYPE_URL,
                        "required": True,
                        "default_value": "https://matrix.org",
                        "sensitive": False
                    },
                    {
                        "key": "access_token",
                        "display_name": "Access Token",
                        "description": "Your Matrix access token. Get this from Element > Settings > Help & About > Advanced.",
                        "type": bi_pb2.FieldType.FIELD_TYPE_PASSWORD,
                        "required": True,
                        "default_value": "",
                        "sensitive": True
                    },
                    {
                        "key": "user_id",
                        "display_name": "User ID",
                        "description": "Your Matrix user ID (e.g., @username:matrix.org)",
                        "type": bi_pb2.FieldType.FIELD_TYPE_STRING,
                        "required": True,
                        "default_value": "",
                        "sensitive": False
                    }
                ],
                "setting_fields": [],
                "example_account_ids": ["@alice:matrix.org", "@bob:example.com"]
            },
            "xmpp": {
                "display_name": "XMPP/Jabber",
                "description": "XMPP (Extensible Messaging and Presence Protocol) is an open standard for messaging and presence.",
                "credential_fields": [
                    {
                        "key": "username",
                        "display_name": "Username",
                        "description": "Your XMPP username (without the @domain part)",
                        "type": bi_pb2.FieldType.FIELD_TYPE_STRING,
                        "required": True,
                        "default_value": "",
                        "sensitive": False
                    },
                    {
                        "key": "password",
                        "display_name": "Password",
                        "description": "Your XMPP account password",
                        "type": bi_pb2.FieldType.FIELD_TYPE_PASSWORD,
                        "required": True,
                        "default_value": "",
                        "sensitive": True
                    },
                    {
                        "key": "server",
                        "display_name": "Server",
                        "description": "Your XMPP server domain (e.g., jabber.org)",
                        "type": bi_pb2.FieldType.FIELD_TYPE_STRING,
                        "required": True,
                        "default_value": "",
                        "sensitive": False
                    },
                    {
                        "key": "port",
                        "display_name": "Port",
                        "description": "XMPP server port (usually 5222 for client connections)",
                        "type": bi_pb2.FieldType.FIELD_TYPE_INTEGER,
                        "required": False,
                        "default_value": "5222",
                        "sensitive": False
                    }
                ],
                "setting_fields": [
                    {
                        "key": "encryption",
                        "display_name": "Encryption",
                        "description": "Connection encryption method",
                        "type": bi_pb2.FieldType.FIELD_TYPE_SELECT,
                        "required": False,
                        "default_value": "starttls",
                        "allowed_values": ["starttls", "direct_tls", "plain"]
                    }
                ],
                "example_account_ids": ["alice@jabber.org", "bob@xmpp.example.com"]
            }
        }
        
        # Get schema definition for this protocol
        schema_def = schema_definitions.get(protocol, {
            "display_name": protocol.title(),
            "description": f"{protocol.title()} protocol support",
            "credential_fields": [],
            "setting_fields": [],
            "example_account_ids": []
        })
        
        # Convert to protobuf fields
        credential_fields = []
        for field_def in schema_def["credential_fields"]:
            field = bi_pb2.CredentialField(
                key=field_def["key"],
                display_name=field_def["display_name"],
                description=field_def["description"],
                type=field_def["type"],
                required=field_def["required"],
                default_value=field_def["default_value"],
                allowed_values=field_def.get("allowed_values", []),
                sensitive=field_def["sensitive"]
            )
            credential_fields.append(field)
        
        setting_fields = []
        for field_def in schema_def.get("setting_fields", []):
            field = bi_pb2.SettingField(
                key=field_def["key"],
                display_name=field_def["display_name"],
                description=field_def["description"],
                type=field_def["type"],
                required=field_def["required"],
                default_value=field_def["default_value"],
                allowed_values=field_def.get("allowed_values", [])
            )
            setting_fields.append(field)
        
        return bi_pb2.ProtocolSchema(
            protocol=protocol,
            display_name=schema_def["display_name"],
            description=schema_def["description"],
            credential_fields=credential_fields,
            setting_fields=setting_fields,
            example_account_ids=schema_def["example_account_ids"]
        )
    
    # Helper methods for plugin communication
    def get_account_configuration(self, protocol: str, account_id: str) -> Optional[PluginConfiguration]:
        """Get the configuration for a specific account plugin instance"""
        account_key = f"{protocol}_{hash(account_id)}"
        if account_key in self.account_credentials:
            plugin_instance = self.plugin_manager.get_plugin_instance(protocol, account_id)
            if plugin_instance and plugin_instance.configuration:
                return plugin_instance.configuration
        return None
    
    def is_account_configured(self, protocol: str, account_id: str) -> bool:
        """Check if an account is properly configured with valid credentials"""
        account_key = f"{protocol}_{hash(account_id)}"
        return (account_key in self.account_credentials and 
                self.account_credentials[account_key].is_valid and 
                self.get_account_configuration(protocol, account_id) is not None)
    
    def get_configured_accounts(self, protocol: str) -> List[AccountCredentials]:
        """Get all configured accounts for a protocol"""
        return [creds for creds in self.account_credentials.values() 
                if creds.protocol == protocol and creds.is_valid]

    async def _notify_plugin_credentials(self, account_creds: AccountCredentials) -> bool:
        """Send credentials to the appropriate plugin instance"""
        success = await self.plugin_manager.initialize_plugin_account(
            account_creds.protocol, 
            account_creds.account_id,
            account_creds.display_name,
            account_creds.credentials
        )
        if success:
            logger.info(f"Plugin instance initialized for {account_creds.account_id} ({account_creds.protocol})")
            # Update the credentials validity if successful
            account_creds.is_valid = True
        else:
            logger.error(f"Failed to initialize plugin instance for {account_creds.account_id} ({account_creds.protocol})")
            # Mark credentials as invalid if initialization failed
            account_creds.is_valid = False
        return success
    
    async def _forward_call_to_plugin(self, call_info: CallInfo):
        """Forward call request to the appropriate plugin instance"""
        # Create call start request
        call_request = cp_pb2.CallStartRequest(
            call_id=call_info.call_id,
            target_address=call_info.target_address,
            camera_stream_url="",  # TODO: Get actual camera stream URL
            camera_capabilities=call_info.preferred_capabilities or common_pb2.MediaCapabilities(),
            player_capabilities=common_pb2.MediaCapabilities()  # TODO: Get actual player capabilities
        )
        
        response = await self.plugin_manager.start_call_on_account(
            call_info.protocol, 
            call_info.account_id, 
            call_request
        )
        if response and response.success:
            # Update call state
            call_info.state = response.state
            logger.info(f"Call {call_info.call_id} forwarded to {call_info.protocol} plugin (account: {call_info.account_id})")
        else:
            call_info.state = common_pb2.CallState.CALL_STATE_FAILED
            logger.error(f"Failed to forward call {call_info.call_id} to {call_info.protocol} plugin (account: {call_info.account_id})")
    
    async def _terminate_call_on_plugin(self, call_info: CallInfo):
        """Request call termination from plugin instance"""
        call_request = cp_pb2.CallEndRequest(
            call_id=call_info.call_id,
            reason="User requested termination"
        )
        
        response = await self.plugin_manager.end_call_on_account(
            call_info.protocol, 
            call_info.account_id, 
            call_request
        )
        if response and response.success:
            logger.info(f"Call {call_info.call_id} terminated on {call_info.protocol} plugin (account: {call_info.account_id})")
        else:
            logger.error(f"Failed to terminate call {call_info.call_id} on {call_info.protocol} plugin (account: {call_info.account_id})")
    
    # Direct callback methods for plugins to call
    def on_contact_added(self, contact: 'common_pb2.Contact'):
        """Called by plugins when a new contact is discovered"""
        logger.info(f"Contact added: {contact.display_name} ({contact.protocol})")
        self.contacts[contact.id] = contact
        # Note: Home Assistant will call StreamContactUpdates to get updated state
    
    def on_contact_updated(self, contact: 'common_pb2.Contact'):
        """Called by plugins when a contact's info changes"""
        logger.info(f"Contact updated: {contact.display_name} ({contact.protocol})")
        self.contacts[contact.id] = contact
        # Note: Home Assistant will call StreamContactUpdates to get updated state
    
    def on_contact_removed(self, contact_id: str, protocol: str):
        """Called by plugins when a contact is no longer available"""
        logger.info(f"Contact removed: {contact_id} ({protocol})")
        self.contacts.pop(contact_id, None)
        # Note: Home Assistant will call StreamContactUpdates to get updated state
    
    def on_call_state_changed(self, call_id: str, new_state: 'common_pb2.CallState.ValueType', metadata: Optional[Dict[str, str]] = None):
        """Called by plugins when a call's state changes"""
        if call_id in self.active_calls:
            self.active_calls[call_id].state = new_state
            logger.info(f"Call {call_id} state changed to {new_state}")
        # Note: Home Assistant will call StreamCallEvents to get updated state
    
    def on_plugin_health_changed(self, protocol: str, healthy: bool, message: str):
        """Called by plugins to report health status changes"""
        logger.info(f"Plugin {protocol} health: {'healthy' if healthy else 'unhealthy'} - {message}")
        # Note: Health status is reported via StreamHealthStatus when requested

async def serve():
    """Start the broker gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    broker = CallAssistBroker()
    
    try:
        add_BrokerIntegrationServicer_to_server(broker, server)
        # Note: CallPlugin service will be added when we implement plugin communication
        
        listen_addr = '[::]:50051'
        server.add_insecure_port(listen_addr)
        
        logger.info(f"Starting Call Assist Broker on {listen_addr}")
        logger.info(f"Available plugins: {broker.plugin_manager.get_available_protocols()}")
        await server.start()
        
        # Wait for termination
        await server.wait_for_termination()
        
    except asyncio.CancelledError:
        # Handle graceful shutdown
        logger.info("Received shutdown signal...")
    finally:
        # Ensure cleanup always happens
        logger.info("Shutting down broker...")
        await broker.plugin_manager.shutdown_all()
        await server.stop(5)

async def main():
    """Main entry point with proper signal handling"""
    try:
        await serve()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Broker failed: {e}")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Broker shutdown complete")
    except Exception as e:
        logger.error(f"Failed to start broker: {e}")
        exit(1)