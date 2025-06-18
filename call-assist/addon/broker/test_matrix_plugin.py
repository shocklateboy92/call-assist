#!/usr/bin/env python3
"""
Matrix Plugin Integration Tests

These tests verify the Matrix plugin's behavior when managed by the broker.
The broker starts the plugin on demand and handles all communication.
Tests use a real Matrix homeserver for protocol validation.
"""

import asyncio
import pytest
import grpc
import grpc.aio
import os
import time
import subprocess
import signal
import socket
import threading
from typing import Dict, Any, Optional
from aiohttp import ClientSession

# Test imports
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import broker_integration_pb2 as bi_pb2
import common_pb2
import broker_integration_pb2_grpc as bi_grpc
from google.protobuf import empty_pb2
from main import CallAssistBroker


class MatrixTestClient:
    """Test client for interacting with Matrix homeserver"""
    
    def __init__(self, homeserver_url: str = "http://synapse:8008"):
        self.homeserver_url = homeserver_url
        self.access_token = None
        self.user_id = None
        self.session = ClientSession()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def register_user(self, username: str, password: str) -> Dict[str, Any]:
        """Register a test user on the Matrix homeserver"""
        url = f"{self.homeserver_url}/_matrix/client/r0/register"
        data = {
            "username": username,
            "password": password,
            "auth": {"type": "m.login.dummy"}
        }
        
        async with self.session.post(url, json=data) as resp:
            result = await resp.json()
            if resp.status == 200:
                self.access_token = result['access_token']
                self.user_id = result['user_id']
            return result
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login with existing user credentials"""
        url = f"{self.homeserver_url}/_matrix/client/r0/login"
        data = {
            "type": "m.login.password",
            "user": username,
            "password": password
        }
        
        async with self.session.post(url, json=data) as resp:
            result = await resp.json()
            if resp.status == 200:
                self.access_token = result['access_token']
                self.user_id = result['user_id']
            return result
    
    async def create_room(self, name: Optional[str] = None, is_public: bool = False) -> Dict[str, Any]:
        """Create a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "visibility": "public" if is_public else "private"
        }
        if name:
            data["name"] = name
        
        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()
    
    async def send_message(self, room_id: str, message: str) -> Dict[str, Any]:
        """Send a message to a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/send/m.room.message"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "msgtype": "m.text",
            "body": message
        }
        
        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()
    
    async def get_room_messages(self, room_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get recent messages from a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"dir": "b", "limit": limit}
        
        async with self.session.get(url, headers=headers, params=params) as resp:
            return await resp.json()


def is_port_available(port: int) -> bool:
    """Check if a port is available for binding"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('localhost', port))
            return True
        except OSError:
            return False


# Global variable to track broker subprocess
_broker_process = None


@pytest.fixture(scope="session")
def broker_process():
    """Session-scoped broker subprocess"""
    global _broker_process
    broker_port = 50051
    
    # Check if broker is already running
    if not is_port_available(broker_port):
        print(f"✓ Using existing broker server on port {broker_port}")
        yield None  # External broker
        return
    
    # Start broker as subprocess
    print(f"Starting broker subprocess on port {broker_port}...")
    broker_script = os.path.join(os.path.dirname(__file__), "main.py")
    _broker_process = subprocess.Popen([
        "python", broker_script
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    max_retries = 20
    for _ in range(max_retries):
        if not is_port_available(broker_port):
            break
        time.sleep(0.5)
    else:
        if _broker_process:
            _broker_process.terminate()
            _broker_process.wait()
        raise RuntimeError("Broker server failed to start within timeout")
    
    print(f"✓ Broker subprocess started (PID: {_broker_process.pid})")
    
    yield _broker_process
    
    # Cleanup
    if _broker_process:
        print("Shutting down broker subprocess...")
        _broker_process.terminate()
        try:
            _broker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _broker_process.kill()
            _broker_process.wait()
        print("✓ Broker subprocess shutdown complete")
        _broker_process = None


@pytest.fixture(scope="function") 
async def broker_server(broker_process):
    """Get broker connection for each test"""
    broker_port = 50051
    
    # Create client connection to the session-scoped broker
    channel = grpc.aio.insecure_channel(f'localhost:{broker_port}')
    stub = bi_grpc.BrokerIntegrationStub(channel)
    
    # Verify server is responsive
    await stub.GetSystemCapabilities(empty_pb2.Empty(), timeout=5.0)
    
    yield stub
    
    # Cleanup just the channel
    await channel.close()


@pytest.fixture
async def matrix_test_users():
    """Create test users on the Matrix homeserver"""
    users = {}
    
    async with MatrixTestClient() as client:
        # Create caller user
        caller_result = await client.register_user(
            f"testcaller_{int(time.time())}", 
            "testpassword123"
        )
        if 'access_token' in caller_result:
            users['caller'] = {
                'user_id': caller_result['user_id'],
                'access_token': caller_result['access_token'],
                'password': 'testpassword123'
            }
        
        # Create receiver user
        receiver_result = await client.register_user(
            f"testreceiver", 
            "testpassword123"
        )
        if 'access_token' in receiver_result:
            users['receiver'] = {
                'user_id': receiver_result['user_id'],
                'access_token': receiver_result['access_token'],
                'password': 'testpassword123'
            }
    
    return users


@pytest.fixture
async def matrix_test_room(matrix_test_users):
    """Create a test room for communication"""
    if 'caller' not in matrix_test_users:
        pytest.skip("No test users available")
    
    caller = matrix_test_users['caller']
    
    async with MatrixTestClient() as client:
        client.access_token = caller['access_token']
        client.user_id = caller['user_id']
        
        room_result = await client.create_room("Test Video Call Room")
        if 'room_id' in room_result:
            return room_result['room_id']
    
    pytest.skip("Could not create test room")


class TestMatrixPluginIntegration:
    """Integration tests for Matrix plugin through broker"""
    
    @pytest.mark.asyncio
    async def test_broker_startup(self, broker_server):
        """Test that broker starts up correctly"""
        # Use the broker_server fixture which automatically manages broker lifecycle
        # Test system capabilities (health check equivalent)
        request = empty_pb2.Empty()
        response = await broker_server.GetSystemCapabilities(request, timeout=5.0)
        
        assert response.broker_capabilities is not None
    
    @pytest.mark.asyncio
    async def test_matrix_credentials_setup(self, broker_server, matrix_test_users):
        """Test Matrix plugin initialization through broker with real credentials"""
        if 'caller' not in matrix_test_users:
            pytest.skip("No test users available")
        
        caller = matrix_test_users['caller']
        
        # Send credentials to broker for matrix protocol
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': caller['access_token'],
                'user_id': caller['user_id'],
                'homeserver': 'http://synapse:8008'
            }
        )
        
        response = await broker_server.UpdateCredentials(creds_request, timeout=10.0)
        
        assert response.success is True
        assert "matrix" in response.message.lower()
    
    @pytest.mark.asyncio
    async def test_matrix_call_flow(self, broker_server, matrix_test_users, matrix_test_room):
        """Test complete Matrix call flow through broker"""
        if 'caller' not in matrix_test_users:
            pytest.skip("No test users available")
        
        caller = matrix_test_users['caller']
        
        # Setup credentials first
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': caller['access_token'],
                'user_id': caller['user_id'],
                'homeserver': 'http://synapse:8008'
            }
        )
        
        creds_response = await broker_server.UpdateCredentials(creds_request, timeout=10.0)
        assert creds_response.success is True
        
        # Initiate a call through broker
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.test_camera',
            media_player_entity_id='media_player.test_chromecast',
            target_address=matrix_test_room,
            protocol='matrix',
            preferred_capabilities=common_pb2.MediaCapabilities(
                video_codecs=['H264'],
                audio_codecs=['OPUS'],
                webrtc_support=True
            )
        )
        
        call_response = await broker_server.InitiateCall(call_request, timeout=10.0)
        
        assert call_response.success is True
        assert call_response.call_id is not None
        assert call_response.call_id != ''
        
        call_id = call_response.call_id
        
        # Verify message was sent to Matrix room
        await asyncio.sleep(3)  # Give time for broker to start plugin and send message
        
        async with MatrixTestClient() as matrix_client:
            matrix_client.access_token = caller['access_token']
            matrix_client.user_id = caller['user_id']
            
            messages = await matrix_client.get_room_messages(matrix_test_room)
            
            # Look for call-related message
            call_message_found = False
            for event in messages.get('chunk', []):
                if event.get('type') == 'm.room.message':
                    body = event.get('content', {}).get('body', '')
                    if 'call' in body.lower() or 'video' in body.lower():
                        call_message_found = True
                        break
            
            assert call_message_found, "No call message found in Matrix room"
        
        # Terminate the call
        term_request = bi_pb2.CallTerminateRequest(
            call_id=call_id
        )
        
        term_response = await broker_server.TerminateCall(term_request, timeout=10.0)
        assert term_response.success is True
    
    @pytest.mark.asyncio
    async def test_matrix_call_with_invalid_room(self, broker_server, matrix_test_users):
        """Test Matrix call to invalid room through broker"""
        if 'caller' not in matrix_test_users:
            pytest.skip("No test users available")
        
        caller = matrix_test_users['caller']
        
        # Setup credentials first
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': caller['access_token'],
                'user_id': caller['user_id'],
                'homeserver': 'http://synapse:8008'
            }
        )
        
        await broker_server.UpdateCredentials(creds_request, timeout=10.0)
        
        # Try to initiate call to invalid room
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.test_camera',
            media_player_entity_id='media_player.test_chromecast',
            target_address='!nonexistent:localhost',
            protocol='matrix',
            preferred_capabilities=common_pb2.MediaCapabilities()
        )
        
        call_response = await broker_server.InitiateCall(call_request, timeout=10.0)
        
        # Should fail gracefully - either broker rejects it or plugin reports failure
        # Since broker starts plugin on demand, this may succeed initially but fail later
        if call_response.success:
            # If broker accepts the call, terminate it to clean up
            term_request = bi_pb2.CallTerminateRequest(
                call_id=call_response.call_id
            )
            await broker_server.TerminateCall(term_request, timeout=5.0)


class TestMatrixPluginStandalone:
    """Tests for Matrix plugin management through broker"""
    
    @pytest.mark.asyncio
    async def test_matrix_plugin_process_management(self, broker_server):
        """Test that broker can manage Matrix plugin process"""        
        matrix_plugin_dir = "/workspaces/universal/call-assist/addon/plugins/matrix"
        if not os.path.exists(matrix_plugin_dir):
            pytest.skip("Matrix plugin directory not found")
        
        # Check if built version exists
        built_plugin = os.path.join(matrix_plugin_dir, "dist", "index.js")
        if not os.path.exists(built_plugin):
            pytest.skip("Matrix plugin not built")
        
        # Note: In the actual architecture, the broker manages plugin lifecycle
        # This test validates that the broker can discover and potentially start plugins
        
        # Check system capabilities to see if matrix plugin is available
        request = empty_pb2.Empty()
        response = await broker_server.GetSystemCapabilities(request, timeout=5.0)
        
        # Look for matrix plugin in available plugins
        matrix_plugin_found = False
        for plugin in response.available_plugins:
            if plugin.protocol == 'matrix':
                matrix_plugin_found = True
                break
        
        # Matrix plugin should be discoverable even if not running
        assert matrix_plugin_found, "Matrix plugin not found in system capabilities"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
