#!/usr/bin/env python3

import asyncio
import logging
import grpc
from concurrent import futures
from typing import Dict, List, Optional

from broker_integration_pb2_grpc import BrokerIntegrationServicer, add_BrokerIntegrationServicer_to_server
from call_plugin_pb2_grpc import CallPluginServicer, add_CallPluginServicer_to_server
import broker_integration_pb2 as bi_pb2
import call_plugin_pb2 as cp_pb2  
import common_pb2
from plugin_manager import PluginManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CallAssistBroker(BrokerIntegrationServicer, CallPluginServicer):
    """
    Main broker service that implements both BrokerIntegration (for HA) 
    and CallPlugin (for managing plugins) services.
    """
    
    def __init__(self):
        self.configuration: Dict = {}
        self.credentials: Dict[str, Dict] = {}  # protocol -> credentials
        self.active_calls: Dict[str, Dict] = {}  # call_id -> call_info
        self.call_counter = 0
        self.plugin_manager = PluginManager()
        
    async def UpdateConfiguration(self, request: bi_pb2.ConfigurationRequest, context) -> bi_pb2.ConfigurationResponse:
        """Update system configuration from Home Assistant"""
        try:
            logger.info(f"Updating configuration: {len(request.camera_entities)} cameras, {len(request.media_player_entities)} media players")
            
            self.configuration = {
                'camera_entities': dict(request.camera_entities),
                'media_player_entities': dict(request.media_player_entities),
                'enabled_protocols': list(request.enabled_protocols)
            }
            
            return bi_pb2.ConfigurationResponse(success=True, message="Configuration updated successfully")
            
        except Exception as e:
            logger.error(f"Configuration update failed: {e}")
            return bi_pb2.ConfigurationResponse(success=False, message=str(e))
    
    async def UpdateCredentials(self, request: bi_pb2.CredentialsRequest, context) -> bi_pb2.CredentialsResponse:
        """Update credentials for a specific protocol"""
        try:
            logger.info(f"Updating credentials for protocol: {request.protocol}")
            
            self.credentials[request.protocol] = dict(request.credentials)
            
            # TODO: Send credentials to the relevant plugin
            await self._notify_plugin_credentials(request.protocol, dict(request.credentials))
            
            return bi_pb2.CredentialsResponse(success=True, message=f"Credentials updated for {request.protocol}")
            
        except Exception as e:
            logger.error(f"Credentials update failed for {request.protocol}: {e}")
            return bi_pb2.CredentialsResponse(success=False, message=str(e))
    
    async def InitiateCall(self, request: bi_pb2.CallRequest, context) -> bi_pb2.CallResponse:
        """Initiate a new call"""
        try:
            self.call_counter += 1
            call_id = f"call_{self.call_counter}"
            
            logger.info(f"Initiating call {call_id}: {request.protocol} to {request.target_address}")
            
            # Store call information
            call_info = {
                'call_id': call_id,
                'camera_entity_id': request.camera_entity_id,
                'media_player_entity_id': request.media_player_entity_id,
                'target_address': request.target_address,
                'protocol': request.protocol,
                'state': common_pb2.CallState.CALL_STATE_INITIATING,
                'preferred_capabilities': request.preferred_capabilities
            }
            
            self.active_calls[call_id] = call_info
            
            # TODO: Forward to appropriate plugin
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
    
    async def StreamCallStatus(self, request, context):
        """Stream call status updates to Home Assistant"""
        logger.info("Starting call status stream")
        
        try:
            while True:
                # TODO: Implement actual event streaming from plugins
                await asyncio.sleep(5)  # Placeholder
                
                # Send periodic health checks for now
                for call_id, call_info in self.active_calls.items():
                    event = common_pb2.CallEvent(
                        call_id=call_id,
                        state=call_info['state'],
                        message=f"Call {call_id} status update"
                    )
                    yield event
                    
        except Exception as e:
            logger.error(f"Call status streaming failed: {e}")
    
    async def StreamSystemHealth(self, request, context):
        """Stream system health status to Home Assistant"""
        logger.info("Starting system health stream")
        
        try:
            while True:
                # Basic health check
                health = common_pb2.HealthStatus(
                    component="broker",
                    status=common_pb2.HealthStatus.Status.HEALTHY,
                    message="Broker running normally"
                )
                yield health
                
                await asyncio.sleep(10)  # Health check every 10 seconds
                
        except Exception as e:
            logger.error(f"Health streaming failed: {e}")
    
    async def GetSystemCapabilities(self, request, context) -> bi_pb2.SystemCapabilities:
        """Get current system capabilities"""
        try:
            # Basic broker capabilities
            broker_caps = common_pb2.MediaCapabilities(
                video_codecs=["H264", "VP8"],
                audio_codecs=["OPUS", "G711"],
                max_resolution="1080p",
                supports_webrtc=True
            )
            
            # Query plugin capabilities
            plugin_caps = []
            available_protocols = self.plugin_manager.get_available_protocols()
            
            for protocol in available_protocols:
                plugin_metadata = self.plugin_manager.get_plugin_info(protocol)
                plugin_state = self.plugin_manager.get_plugin_state(protocol)
                
                # Convert plugin metadata capabilities to protobuf
                caps = plugin_metadata.capabilities if plugin_metadata else {}
                plugin_media_caps = common_pb2.MediaCapabilities(
                    video_codecs=caps.get('video_codecs', []),
                    audio_codecs=caps.get('audio_codecs', []),
                    max_resolution=caps.get('max_resolution', '720p'),
                    supports_webrtc=caps.get('supports_webrtc', False)
                )
                
                plugin_caps.append(bi_pb2.PluginCapabilities(
                    protocol=protocol,
                    available=(protocol in self.credentials and plugin_state.value != 'error'),
                    capabilities=plugin_media_caps
                ))
            
            return bi_pb2.SystemCapabilities(
                broker_capabilities=broker_caps,
                available_plugins=plugin_caps
            )
            
        except Exception as e:
            logger.error(f"Capability query failed: {e}")
            return bi_pb2.SystemCapabilities()
    
    # Helper methods for plugin communication
    async def _notify_plugin_credentials(self, protocol: str, credentials: Dict):
        """Send credentials to the appropriate plugin"""
        success = await self.plugin_manager.initialize_plugin(protocol, credentials)
        if success:
            logger.info(f"Plugin {protocol} initialized with credentials")
        else:
            logger.error(f"Failed to initialize plugin {protocol}")
    
    async def _forward_call_to_plugin(self, call_info: Dict):
        """Forward call request to the appropriate plugin"""
        protocol = call_info['protocol']
        
        # Create call start request
        call_request = cp_pb2.CallStartRequest(
            call_id=call_info['call_id'],
            target_address=call_info['target_address'],
            camera_stream_url="",  # TODO: Get actual camera stream URL
            camera_capabilities=call_info.get('preferred_capabilities', common_pb2.MediaCapabilities()),
            player_capabilities=common_pb2.MediaCapabilities()  # TODO: Get actual player capabilities
        )
        
        response = await self.plugin_manager.start_call(protocol, call_request)
        if response and response.success:
            # Update call state
            call_info['state'] = response.state
            logger.info(f"Call {call_info['call_id']} forwarded to {protocol} plugin")
        else:
            call_info['state'] = common_pb2.CallState.CALL_STATE_FAILED
            logger.error(f"Failed to forward call {call_info['call_id']} to {protocol} plugin")
    
    async def _terminate_call_on_plugin(self, call_info: Dict):
        """Request call termination from plugin"""
        protocol = call_info['protocol']
        
        call_request = cp_pb2.CallEndRequest(
            call_id=call_info['call_id'],
            reason="User requested termination"
        )
        
        response = await self.plugin_manager.end_call(protocol, call_request)
        if response and response.success:
            logger.info(f"Call {call_info['call_id']} terminated on {protocol} plugin")
        else:
            logger.error(f"Failed to terminate call {call_info['call_id']} on {protocol} plugin")

async def serve():
    """Start the broker gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    
    broker = CallAssistBroker()
    add_BrokerIntegrationServicer_to_server(broker, server)
    # Note: CallPlugin service will be added when we implement plugin communication
    
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting Call Assist Broker on {listen_addr}")
    logger.info(f"Available plugins: {broker.plugin_manager.get_available_protocols()}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down broker...")
        await broker.plugin_manager.shutdown_all()
        await server.stop(5)

if __name__ == '__main__':
    asyncio.run(serve())