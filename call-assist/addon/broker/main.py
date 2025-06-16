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
        self.plugin_connections: Dict[str, grpc.Channel] = {}  # protocol -> channel
        self.call_counter = 0
        
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
            # TODO: Query actual capabilities from plugins and system
            broker_caps = common_pb2.MediaCapabilities(
                video_codecs=["H264", "VP8"],
                audio_codecs=["OPUS", "G711"],
                max_resolution="1080p",
                supports_webrtc=True
            )
            
            plugin_caps = []
            for protocol in self.configuration.get('enabled_protocols', []):
                plugin_caps.append(bi_pb2.PluginCapabilities(
                    protocol=protocol,
                    available=protocol in self.credentials,
                    capabilities=broker_caps  # Placeholder
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
        # TODO: Implement plugin communication
        logger.info(f"TODO: Send credentials to {protocol} plugin")
    
    async def _forward_call_to_plugin(self, call_info: Dict):
        """Forward call request to the appropriate plugin"""
        # TODO: Implement plugin communication
        protocol = call_info['protocol']
        logger.info(f"TODO: Forward call to {protocol} plugin")
    
    async def _terminate_call_on_plugin(self, call_info: Dict):
        """Request call termination from plugin"""
        # TODO: Implement plugin communication
        protocol = call_info['protocol']
        logger.info(f"TODO: Terminate call on {protocol} plugin")

async def serve():
    """Start the broker gRPC server"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    
    broker = CallAssistBroker()
    add_BrokerIntegrationServicer_to_server(broker, server)
    # Note: CallPlugin service will be added when we implement plugin communication
    
    listen_addr = '[::]:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"Starting Call Assist Broker on {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down broker...")
        await server.stop(5)

if __name__ == '__main__':
    asyncio.run(serve())