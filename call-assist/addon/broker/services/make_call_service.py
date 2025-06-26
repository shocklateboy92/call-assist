#!/usr/bin/env python3
"""
Make call service implementation.

This service allows starting video calls given a contact and call station.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from fastapi import Depends
from sqlmodel import Session

from addon.broker.service_registry import BrokerService, ServiceConfig, ServiceFieldConfig
from addon.broker.dependencies import get_database_session, get_plugin_manager
from addon.broker.plugin_manager import PluginManager
from addon.broker.queries import get_call_station_by_id_with_session, log_call_start_with_session
from addon.broker.models import CallStation
from proto_gen.callassist.plugin import CallStartRequest

logger = logging.getLogger(__name__)


class MakeCallService(BrokerService):
    """Service for initiating video calls."""
    
    def __init__(
        self,
        plugin_manager: PluginManager,
        database_session: Optional[Session] = None,
        available_call_stations: Optional[List[Dict[str, str]]] = None,
        available_contacts: Optional[List[Dict[str, str]]] = None
    ):
        self.plugin_manager = plugin_manager
        self.database_session = database_session
        self.available_call_stations = available_call_stations or []
        self.available_contacts = available_contacts or []
        
        # Create field configurations with dynamic options
        self._call_station_id_config = ServiceFieldConfig(
            display_name="Call Station",
            description="The call station to use for the video call",
            required=True,
            options=[
                f"{station['station_id']}:{station['display_name']}" 
                for station in self.available_call_stations
            ]
        )
        
        self._contact_id_config = ServiceFieldConfig(
            display_name="Contact",
            description="The contact to call",
            required=True,
            options=[
                f"{contact['contact_id']}:{contact['display_name']}" 
                for contact in self.available_contacts
            ]
        )
        
        self._duration_minutes_config = ServiceFieldConfig(
            display_name="Max Duration (minutes)",
            description="Maximum call duration in minutes (0 for unlimited)",
            required=False,
            default_value="30"
        )
        
        super().__init__(ServiceConfig(
            display_name="Make Video Call",
            description="Initiate a video call using a call station to a contact",
            icon="mdi:video-account",
            required_capabilities=["make_call"]
        ))
        
        # Register field configurations
        self._field_configs['call_station_id'] = self._call_station_id_config
        self._field_configs['contact_id'] = self._contact_id_config
        self._field_configs['duration_minutes'] = self._duration_minutes_config
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the make call service."""
        
        call_station_id = kwargs.get('call_station_id', '')
        contact_id = kwargs.get('contact_id', '')
        duration_minutes = int(kwargs.get('duration_minutes', 30))
        
        logger.info(f"Making call from station {call_station_id} to contact {contact_id}")
        
        try:
            # Parse the call station ID (format: "station_id:display_name")
            actual_station_id = call_station_id.split(':')[0] if ':' in call_station_id else call_station_id
            
            # Get call station from database
            call_station = None
            if self.database_session is None:
                # Fallback without database lookup
                logger.warning("No database session available, using stub call station data")
                for station in self.available_call_stations:
                    if station['station_id'] == actual_station_id:
                        # Create a mock call station object with proper attributes
                        call_station = CallStation(
                            station_id=actual_station_id,
                            display_name=station['display_name'],
                            enabled=True,
                            camera_entity_id=f"camera.{actual_station_id}",
                            media_player_entity_id=f"media_player.{actual_station_id}"
                        )
                        break
            else:
                call_station = get_call_station_by_id_with_session(self.database_session, actual_station_id)
                
            if not call_station:
                return {
                    'message': f"Call station '{actual_station_id}' not found",
                    'data': {}
                }

            if not call_station.enabled:
                return {
                    'message': f"Call station '{call_station.display_name}' is disabled",
                    'data': {}
                }
            
            # Parse contact ID (format: "contact_id:display_name" or protocol specific format)
            actual_contact_id = contact_id.split(':')[0] if ':' in contact_id else contact_id
            
            # Find the contact in available contacts to get protocol
            contact_info = None
            for contact in self.available_contacts:
                if contact['id'] == actual_contact_id:
                    contact_info = contact
                    break
            
            if not contact_info:
                return {
                    'message': f"Contact '{actual_contact_id}' not found",
                    'data': {}
                }
            
            # Get the protocol for this contact
            protocol = contact_info.get('protocol')
            if not protocol:
                return {
                    'message': f"No protocol specified for contact '{actual_contact_id}'",
                    'data': {}
                }
            
            # Check if plugin is available
            if protocol not in self.plugin_manager.get_available_protocols():
                return {
                    'message': f"Protocol '{protocol}' plugin is not available",
                    'data': {}
                }
            
            # Generate unique call ID
            call_id = str(uuid.uuid4())
            
            # Create call start request
            call_request = CallStartRequest(
                call_id=call_id,
                target_address=actual_contact_id,
                camera_stream_url=f"rtsp://fake-stream-url/{call_station.camera_entity_id}",
                # TODO: Get actual capabilities from entities
            )
            
            # Log call start (if database available)
            if self.database_session:
                log_call_start_with_session(
                    session=self.database_session,
                    call_id=call_id,
                    protocol=protocol,
                    account_id=contact_info.get('account_id', ''),
                    target_address=actual_contact_id,
                    camera_entity_id=call_station.camera_entity_id,
                    media_player_entity_id=call_station.media_player_entity_id
                )
            
            # Initiate the call via plugin manager
            call_result = await self.plugin_manager.start_call(protocol, call_request)
            
            if call_result and call_result.success:
                return {
                    'message': f"Call initiated successfully to {contact_info.get('display_name', actual_contact_id)}",
                    'data': {
                        'call_id': call_id,
                        'call_station': call_station.display_name,
                        'contact': contact_info.get('display_name', actual_contact_id),
                        'protocol': protocol,
                        'max_duration_minutes': str(duration_minutes)
                    }
                }
            else:
                error_msg = call_result.message if call_result else 'Failed to initiate call'
                return {
                    'message': error_msg,
                    'data': {}
                }
                
        except Exception as ex:
            logger.error(f"Error executing make call service: {ex}")
            return {
                'message': f"Service execution failed: {str(ex)}",
                'data': {}
            }


async def create_make_call_service(
    plugin_manager: PluginManager = Depends(get_plugin_manager),
    database_session: Session = Depends(get_database_session)
) -> MakeCallService:
    """Factory function to create MakeCallService with current data."""
    
    # Get available call stations (simplified for now)
    # TODO: Get from broker state when available
    available_call_stations = [
        {'station_id': 'test_station', 'display_name': 'Test Station'}
    ]
    
    # Get available contacts (simplified for now)  
    # TODO: Get from plugin manager when contact discovery is implemented
    available_contacts = [
        {'id': '@test:matrix.org', 'display_name': 'Test Contact', 'protocol': 'matrix', 'account_id': '@user:matrix.org'}
    ]
    
    return MakeCallService(
        plugin_manager=plugin_manager,
        database_session=database_session,
        available_call_stations=available_call_stations,
        available_contacts=available_contacts
    )
