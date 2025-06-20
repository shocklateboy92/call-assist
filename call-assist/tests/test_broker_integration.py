#!/usr/bin/env python3
"""
Integration tests for the Call Assist Broker.
These tests verify the complete flow from broker to matrix plugin.
"""

import asyncio
import pytest
import grpc
import grpc.aio
import subprocess
import time
import os
import tempfile
import yaml
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, Mock, patch

# Import broker and proto files
from addon.broker.main import CallAssistBroker
from addon.broker.plugin_manager import PluginManager, PluginInstance, PluginMetadata, PluginState
import proto_gen.broker_integration_pb2 as bi_pb2
import proto_gen.call_plugin_pb2 as cp_pb2
import proto_gen.common_pb2 as common_pb2
import proto_gen.broker_integration_pb2_grpc as bi_grpc


class MockMatrixPlugin:
    """Mock Matrix plugin for testing"""
    
    def __init__(self, port: int = 50052):
        self.port = port
        self.server = None
        self.initialized = False
        self.active_calls = {}
        self.credentials = {}
        
    async def start(self):
        """Start the mock matrix plugin gRPC server"""
        self.server = grpc.aio.server()
        
        # Add the call plugin service
        from proto_gen.call_plugin_pb2_grpc import add_CallPluginServicer_to_server
        add_CallPluginServicer_to_server(self, self.server)
        
        listen_addr = f'[::]:{self.port}'
        self.server.add_insecure_port(listen_addr)
        await self.server.start()
        
    async def stop(self):
        """Stop the mock matrix plugin"""
        if self.server:
            await self.server.stop(5)
    
    # gRPC service methods
    async def Initialize(self, request, context):
        """Initialize the mock plugin with credentials"""
        self.credentials = dict(request.credentials)
        self.initialized = True
        
        # Simulate validation
        has_required_creds = ('access_token' in self.credentials and 
                             'user_id' in self.credentials)
        
        return cp_pb2.PluginStatus(
            initialized=has_required_creds,
            authenticated=has_required_creds,
            message="Mock Matrix plugin initialized" if has_required_creds else "Missing required credentials",
            capabilities=common_pb2.MediaCapabilities(
                video_codecs=['H264', 'VP8'],
                audio_codecs=['OPUS', 'G711'],
                supported_resolutions=[
                    common_pb2.Resolution(width=1280, height=720, framerate=30)
                ],
                webrtc_support=True
            )
        )
    
    async def Shutdown(self, request, context):
        """Shutdown the mock plugin"""
        self.initialized = False
        self.active_calls.clear()
        from google.protobuf import empty_pb2
        return empty_pb2.Empty()
    
    async def StartCall(self, request, context):
        """Start a mock call"""
        if not self.initialized:
            return cp_pb2.CallStartResponse(
                success=False,
                message="Plugin not initialized",
                state=common_pb2.CallState.CALL_STATE_FAILED
            )
        
        call_id = request.call_id
        self.active_calls[call_id] = {
            'target_address': request.target_address,
            'state': common_pb2.CallState.CALL_STATE_CONNECTING,
            'start_time': time.time()
        }
        
        # Simulate successful call start
        return cp_pb2.CallStartResponse(
            success=True,
            message="Mock call started",
            state=common_pb2.CallState.CALL_STATE_CONNECTING,
            remote_stream_url="mock://remote.stream"
        )
    
    async def AcceptCall(self, request, context):
        """Accept a mock call"""
        call_id = request.call_id
        if call_id in self.active_calls:
            self.active_calls[call_id]['state'] = common_pb2.CallState.CALL_STATE_ACTIVE
            return cp_pb2.CallAcceptResponse(
                success=True,
                message="Mock call accepted",
                remote_stream_url="mock://accepted.stream"
            )
        else:
            return cp_pb2.CallAcceptResponse(
                success=False,
                message="Call not found"
            )
    
    async def EndCall(self, request, context):
        """End a mock call"""
        call_id = request.call_id
        
        if call_id not in self.active_calls:
            return cp_pb2.CallEndResponse(
                success=False,
                message="Call not found"
            )
        
        del self.active_calls[call_id]
        
        return cp_pb2.CallEndResponse(
            success=True,
            message="Mock call ended"
        )
    
    async def NegotiateMedia(self, request, context):
        """Negotiate media capabilities"""
        return common_pb2.MediaNegotiation(
            selected_video_codec="H264",
            selected_audio_codec="OPUS",
            selected_resolution=common_pb2.Resolution(width=1280, height=720, framerate=30),
            direct_streaming=True,
            transcoding_required=False,
            stream_url="mock://negotiated.stream"
        )
    
    async def StreamCallEvents(self, request, context):
        """Stream call events (mock implementation)"""
        # This would normally stream real events, but for testing we'll just yield nothing
        return
        yield  # Make this a generator function
    
    async def GetHealth(self, request, context):
        """Return health status"""
        return common_pb2.HealthStatus(
            healthy=self.initialized,
            component="mock_matrix_plugin",
            message="Mock plugin is " + ("healthy" if self.initialized else "unhealthy")
        )


@pytest.fixture
async def mock_matrix_plugin():
    """Fixture that provides a mock matrix plugin"""
    plugin = MockMatrixPlugin()
    await plugin.start()
    yield plugin
    await plugin.stop()


@pytest.fixture
def temp_plugin_dir():
    """Create a temporary plugin directory with mock plugin metadata"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock matrix plugin directory
        matrix_dir = os.path.join(temp_dir, "matrix")
        os.makedirs(matrix_dir)
        
        # Create plugin.yaml
        plugin_config = {
            'name': 'Matrix Call Plugin',
            'protocol': 'matrix',
            'version': '1.0.0',
            'description': 'Matrix protocol plugin for video calls',
            'executable': {
                'type': 'node',
                'command': ['node', 'dist/index.js'],
                'working_directory': '.'
            },
            'grpc': {
                'port': 50052,
                'health_check_timeout': 5,
                'startup_timeout': 30
            },
            'capabilities': {
                'video_codecs': ['H264', 'VP8'],
                'audio_codecs': ['OPUS', 'G711'],
                'supported_resolutions': [
                    {'width': 1920, 'height': 1080, 'framerate': 30},
                    {'width': 1280, 'height': 720, 'framerate': 30}
                ],
                'webrtc_support': True
            },
            'required_credentials': ['access_token', 'user_id', 'homeserver']
        }
        
        with open(os.path.join(matrix_dir, 'plugin.yaml'), 'w') as f:
            yaml.dump(plugin_config, f)
        
        yield temp_dir


@pytest.fixture
async def broker_with_mock_plugin(temp_plugin_dir, mock_matrix_plugin):
    """Fixture that provides a broker with mocked plugin manager"""
    broker = CallAssistBroker()
    
    # Replace plugin manager with one using temp directory
    broker.plugin_manager = PluginManager(plugins_root=temp_plugin_dir)
    
    # Mock the plugin startup to connect to our mock plugin
    async def mock_start_plugin(plugin):
        """Mock plugin startup that connects to our mock plugin"""
        plugin.state = PluginState.RUNNING
        
        # Create gRPC channel to mock plugin
        channel = grpc.aio.insecure_channel(f'localhost:{mock_matrix_plugin.port}')
        plugin.channel = channel
        
        from proto_gen.call_plugin_pb2_grpc import CallPluginStub
        plugin.stub = CallPluginStub(channel)
        
        return True
    
    # Patch the plugin manager's _start_plugin method
    broker.plugin_manager._start_plugin = mock_start_plugin
    
    yield broker


@pytest.mark.integration
class TestBrokerIntegration:
    """Integration tests for the Call Assist Broker"""
    
    @pytest.mark.asyncio
    async def test_broker_startup_and_plugin_discovery(self, temp_plugin_dir):
        """Test that broker starts up and discovers plugins correctly"""
        broker = CallAssistBroker()
        broker.plugin_manager = PluginManager(plugins_root=temp_plugin_dir)
        
        # Check that matrix plugin was discovered
        assert 'matrix' in broker.plugin_manager.plugins
        plugin = broker.plugin_manager.plugins['matrix']
        assert plugin.metadata.name == 'Matrix Call Plugin'
        assert plugin.metadata.protocol == 'matrix'
        assert plugin.state == PluginState.STOPPED
    
    @pytest.mark.asyncio
    async def test_configuration_update(self, broker_with_mock_plugin):
        """Test updating broker configuration"""
        broker = broker_with_mock_plugin
        
        # Create configuration request
        request = bi_pb2.ConfigurationRequest(
            camera_entities={
                'camera.front_door': 'rtsp://192.168.1.100/stream',
                'camera.living_room': 'rtsp://192.168.1.101/stream'
            },
            media_player_entities={
                'media_player.living_room_tv': 'chromecast',
                'media_player.bedroom_display': 'nest_hub'
            },
            enabled_protocols=['matrix']
        )
        
        response = await broker.UpdateConfiguration(request, None)
        
        assert response.success is True
        assert broker.configuration is not None
        assert len(broker.configuration.camera_entities) == 2
        assert len(broker.configuration.media_player_entities) == 2
        assert 'matrix' in broker.configuration.enabled_protocols
    
    @pytest.mark.asyncio
    async def test_credentials_update_and_plugin_initialization(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test updating credentials and initializing plugin"""
        broker = broker_with_mock_plugin
        
        # Update credentials for matrix
        request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_access_token_12345',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        
        response = await broker.UpdateCredentials(request, None)
        
        assert response.success is True
        assert 'matrix' in broker.credentials
        
        # Verify credentials were passed to plugin
        assert mock_matrix_plugin.initialized is True
        assert mock_matrix_plugin.credentials['access_token'] == 'test_access_token_12345'
        assert mock_matrix_plugin.credentials['user_id'] == '@testuser:matrix.org'
    
    @pytest.mark.asyncio
    async def test_call_initiation_full_flow(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test complete call initiation flow"""
        broker = broker_with_mock_plugin
        
        # First, set up configuration
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={'camera.front_door': 'rtsp://192.168.1.100/stream'},
            media_player_entities={'media_player.living_room_tv': 'chromecast'},
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        # Set up credentials
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Initiate a call
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.front_door',
            media_player_entity_id='media_player.living_room_tv',
            target_address='!roomid:matrix.org',
            protocol='matrix',
            preferred_capabilities=common_pb2.MediaCapabilities(
                video_codecs=['H264'],
                audio_codecs=['OPUS']
            )
        )
        
        response = await broker.InitiateCall(call_request, None)
        
        assert response.success is True
        assert response.call_id.startswith('call_')
        assert response.initial_state == common_pb2.CallState.CALL_STATE_INITIATING
        
        # Verify call was registered in broker
        assert response.call_id in broker.active_calls
        call_info = broker.active_calls[response.call_id]
        assert call_info.protocol == 'matrix'
        assert call_info.target_address == '!roomid:matrix.org'
        
        # Verify call was forwarded to plugin
        await asyncio.sleep(0.1)  # Give async processing time
        assert len(mock_matrix_plugin.active_calls) == 1
    
    @pytest.mark.asyncio
    async def test_call_termination(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test call termination flow"""
        broker = broker_with_mock_plugin
        
        # Set up configuration and credentials
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={'camera.front_door': 'rtsp://192.168.1.100/stream'},
            media_player_entities={'media_player.living_room_tv': 'chromecast'},
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Start a call
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.front_door',
            media_player_entity_id='media_player.living_room_tv',
            target_address='!roomid:matrix.org',
            protocol='matrix'
        )
        
        call_response = await broker.InitiateCall(call_request, None)
        call_id = call_response.call_id
        
        # Wait for call to be processed
        await asyncio.sleep(0.1)
        
        # Terminate the call
        terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
        terminate_response = await broker.TerminateCall(terminate_request, None)
        
        assert terminate_response.success is True
        
        # Verify call was removed from broker
        assert call_id not in broker.active_calls
        
        # Verify call was terminated in plugin
        assert len(mock_matrix_plugin.active_calls) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_calls(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test handling multiple concurrent calls"""
        broker = broker_with_mock_plugin
        
        # Set up configuration and credentials
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={
                'camera.front_door': 'rtsp://192.168.1.100/stream',
                'camera.back_door': 'rtsp://192.168.1.101/stream'
            },
            media_player_entities={
                'media_player.living_room_tv': 'chromecast',
                'media_player.bedroom_display': 'nest_hub'
            },
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Start multiple calls
        call_requests = [
            bi_pb2.CallRequest(
                camera_entity_id='camera.front_door',
                media_player_entity_id='media_player.living_room_tv',
                target_address='!room1:matrix.org',
                protocol='matrix'
            ),
            bi_pb2.CallRequest(
                camera_entity_id='camera.back_door',
                media_player_entity_id='media_player.bedroom_display',
                target_address='!room2:matrix.org',
                protocol='matrix'
            )
        ]
        
        call_ids = []
        for request in call_requests:
            response = await broker.InitiateCall(request, None)
            assert response.success is True
            call_ids.append(response.call_id)
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        # Verify both calls are active
        assert len(broker.active_calls) == 2
        assert len(mock_matrix_plugin.active_calls) == 2
        
        # Terminate one call
        terminate_request = bi_pb2.CallTerminateRequest(call_id=call_ids[0])
        terminate_response = await broker.TerminateCall(terminate_request, None)
        assert terminate_response.success is True
        
        # Verify only one call remains
        assert len(broker.active_calls) == 1
        assert call_ids[1] in broker.active_calls
    
    @pytest.mark.asyncio
    async def test_system_capabilities_query(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test querying system capabilities"""
        broker = broker_with_mock_plugin
        
        # Set up credentials so plugin is initialized
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Query capabilities
        from google.protobuf import empty_pb2
        request = empty_pb2.Empty()
        response = await broker.GetSystemCapabilities(request, None)
        
        assert response.broker_capabilities is not None
        assert len(response.available_plugins) >= 1
        
        # Find matrix plugin capabilities
        matrix_caps = None
        for plugin_cap in response.available_plugins:
            if plugin_cap.protocol == 'matrix':
                matrix_caps = plugin_cap
                break
        
        assert matrix_caps is not None
        assert matrix_caps.available is True
        assert 'H264' in matrix_caps.capabilities.video_codecs
        assert matrix_caps.capabilities.webrtc_support is True
    
    @pytest.mark.asyncio
    async def test_invalid_credentials_handling(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test handling of invalid credentials"""
        broker = broker_with_mock_plugin
        
        # Try to update with incomplete credentials
        request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token'
                # Missing user_id and homeserver
            }
        )
        
        response = await broker.UpdateCredentials(request, None)
        
        # Should still update in broker but plugin initialization should fail
        assert response.success is True  # Broker accepts the update
        assert 'matrix' in broker.credentials
        
        # But plugin should not be successfully initialized
        assert mock_matrix_plugin.initialized is False
    
    @pytest.mark.asyncio
    async def test_call_to_nonexistent_plugin(self, broker_with_mock_plugin):
        """Test attempting to call with a non-existent plugin"""
        broker = broker_with_mock_plugin
        
        # Try to initiate call with unsupported protocol
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.front_door',
            media_player_entity_id='media_player.living_room_tv',
            target_address='sip:user@example.com',
            protocol='sip'  # This protocol doesn't exist
        )
        
        response = await broker.InitiateCall(call_request, None)
        
        # Should fail gracefully
        assert response.success is False
        assert 'sip' not in broker.active_calls


class TestUserScenarios:
    """End-to-end user scenarios testing"""
    
    @pytest.mark.asyncio
    async def test_doorbell_scenario(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test doorbell ring -> video call scenario"""
        broker = broker_with_mock_plugin
        
        # Setup: Home Assistant has a doorbell camera and living room TV
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={'camera.doorbell': 'rtsp://192.168.1.50/stream'},
            media_player_entities={'media_player.living_room_chromecast': 'chromecast'},
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        # Setup: User has configured Matrix credentials
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'homeowner_access_token',
                'user_id': '@homeowner:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Scenario: Doorbell rings, user wants to see who it is
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.doorbell',
            media_player_entity_id='media_player.living_room_chromecast',
            target_address='@visitor:matrix.org',  # Visitor's Matrix ID
            protocol='matrix',
            preferred_capabilities=common_pb2.MediaCapabilities(
                video_codecs=['H264'],
                audio_codecs=['OPUS'],
                supported_resolutions=[
                    common_pb2.Resolution(width=1280, height=720, framerate=30)
                ]
            )
        )
        
        response = await broker.InitiateCall(call_request, None)
        
        assert response.success is True
        call_id = response.call_id
        
        # Verify call is active
        await asyncio.sleep(0.1)
        assert call_id in broker.active_calls
        assert len(mock_matrix_plugin.active_calls) == 1
        
        # Simulate visitor answering
        # (In real scenario, this would come from Matrix events)
        
        # Later: User ends the call
        terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
        terminate_response = await broker.TerminateCall(terminate_request, None)
        
        assert terminate_response.success is True
        assert call_id not in broker.active_calls
    
    @pytest.mark.asyncio
    async def test_security_monitoring_scenario(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test security monitoring with multiple cameras"""
        broker = broker_with_mock_plugin
        
        # Setup: Multiple security cameras
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={
                'camera.front_yard': 'rtsp://192.168.1.60/stream',
                'camera.back_yard': 'rtsp://192.168.1.61/stream',
                'camera.garage': 'rtsp://192.168.1.62/stream'
            },
            media_player_entities={
                'media_player.security_monitor': 'nvidia_shield',
                'media_player.mobile_phone': 'android_cast'
            },
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        # Setup: Security team Matrix credentials
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'security_team_token',
                'user_id': '@security:company.matrix.org',
                'homeserver': 'https://company.matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Scenario: Motion detected on multiple cameras, start calls to security room
        security_room = '!security-alerts:company.matrix.org'
        
        camera_calls = []
        for camera_id in ['camera.front_yard', 'camera.back_yard', 'camera.garage']:
            call_request = bi_pb2.CallRequest(
                camera_entity_id=camera_id,
                media_player_entity_id='media_player.security_monitor',
                target_address=security_room,
                protocol='matrix'
            )
            
            response = await broker.InitiateCall(call_request, None)
            assert response.success is True
            camera_calls.append(response.call_id)
        
        # Verify all calls are active
        await asyncio.sleep(0.1)
        assert len(broker.active_calls) == 3
        assert len(mock_matrix_plugin.active_calls) == 3
        
        # Scenario: Security team reviews and ends calls one by one
        for call_id in camera_calls:
            terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
            terminate_response = await broker.TerminateCall(terminate_request, None)
            assert terminate_response.success is True
        
        # All calls should be terminated
        assert len(broker.active_calls) == 0
        assert len(mock_matrix_plugin.active_calls) == 0
    
    @pytest.mark.asyncio
    async def test_family_communication_scenario(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test family intercom system scenario"""
        broker = broker_with_mock_plugin
        
        # Setup: Kitchen display and bedroom displays with cameras
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={
                'camera.kitchen_display': 'v4l2:///dev/video0',
                'camera.bedroom_display': 'v4l2:///dev/video1'
            },
            media_player_entities={
                'media_player.kitchen_hub': 'nest_hub',
                'media_player.bedroom_hub': 'nest_hub'
            },
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        # Setup: Family Matrix server credentials
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'family_home_token',
                'user_id': '@home-assistant:family.matrix.org',
                'homeserver': 'https://family.matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)
        
        # Scenario: Parent in kitchen wants to call kids in bedroom
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.kitchen_display',
            media_player_entity_id='media_player.bedroom_hub',
            target_address='!kids-room:family.matrix.org',
            protocol='matrix',
            preferred_capabilities=common_pb2.MediaCapabilities(
                video_codecs=['H264'],
                audio_codecs=['OPUS'],
                webrtc_support=True
            )
        )
        
        response = await broker.InitiateCall(call_request, None)
        assert response.success is True
        
        # Verify call setup
        await asyncio.sleep(0.1)
        assert response.call_id in broker.active_calls
        call_info = broker.active_calls[response.call_id]
        assert call_info.camera_entity_id == 'camera.kitchen_display'
        assert call_info.media_player_entity_id == 'media_player.bedroom_hub'
        
        # Simulate brief family conversation, then end call
        await asyncio.sleep(0.5)  # Simulate call duration
        
        terminate_request = bi_pb2.CallTerminateRequest(call_id=response.call_id)
        terminate_response = await broker.TerminateCall(terminate_request, None)
        assert terminate_response.success is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
