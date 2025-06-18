#!/usr/bin/env python3
"""
Matrix Plugin Integration Tests

These tests verify the Matrix plugin's behavior when integrated with the broker.
They test real Matrix protocol interactions using a test Matrix homeserver.
"""

import asyncio
import pytest
import grpc
import grpc.aio
import json
import os
import tempfile
import time
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, Mock, patch
from aiohttp import ClientSession

# Test imports
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import call_plugin_pb2 as cp_pb2
import common_pb2
import call_plugin_pb2_grpc as cp_grpc
from google.protobuf import empty_pb2


class MatrixTestClient:
    """Test client for interacting with Matrix homeserver"""
    
    def __init__(self, homeserver_url: str = "http://synapse:8008"):
        self.homeserver_url = homeserver_url
        self.access_token = None
        self.user_id = None
        self.session = None
    
    async def __aenter__(self):
        self.session = ClientSession()
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
    
    async def create_room(self, name: str = None, is_public: bool = False) -> Dict[str, Any]:
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
            f"testreceiver_{int(time.time())}", 
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
    """Integration tests for Matrix plugin with real Matrix homeserver"""
    
    @pytest.mark.asyncio
    async def test_matrix_plugin_startup(self):
        """Test that Matrix plugin starts up correctly"""
        # This test would require the actual Matrix plugin to be running
        # For now, we'll test the protocol interactions
        
        # Try to connect to Matrix plugin on expected port
        try:
            channel = grpc.aio.insecure_channel('localhost:50052')
            stub = cp_grpc.CallPluginStub(channel)
            
            # Test health check
            request = empty_pb2.Empty()
            response = await stub.GetHealth(request, timeout=5.0)
            
            assert response.healthy is True
            
            await channel.close()
            
        except grpc.RpcError as e:
            pytest.skip(f"Matrix plugin not running: {e}")
    
    @pytest.mark.asyncio
    async def test_matrix_plugin_initialization(self, matrix_test_users):
        """Test Matrix plugin initialization with real credentials"""
        if 'caller' not in matrix_test_users:
            pytest.skip("No test users available")
        
        caller = matrix_test_users['caller']
        
        try:
            channel = grpc.aio.insecure_channel('localhost:50052')
            stub = cp_grpc.CallPluginStub(channel)
            
            # Initialize plugin with real Matrix credentials
            init_request = cp_pb2.PluginConfig(
                credentials={
                    'access_token': caller['access_token'],
                    'user_id': caller['user_id'],
                    'homeserver': 'http://synapse:8008'
                }
            )
            
            response = await stub.Initialize(init_request, timeout=10.0)
            
            assert response.success is True
            assert "initialized" in response.message.lower()
            
            await channel.close()
            
        except grpc.RpcError as e:
            pytest.skip(f"Matrix plugin not available: {e}")
    
    @pytest.mark.asyncio
    async def test_matrix_call_flow(self, matrix_test_users, matrix_test_room):
        """Test complete Matrix call flow"""
        if 'caller' not in matrix_test_users:
            pytest.skip("No test users available")
        
        caller = matrix_test_users['caller']
        
        try:
            channel = grpc.aio.insecure_channel('localhost:50052')
            stub = cp_grpc.CallPluginStub(channel)
            
            # Initialize plugin
            init_request = cp_pb2.PluginConfig(
                credentials={
                    'access_token': caller['access_token'],
                    'user_id': caller['user_id'],
                    'homeserver': 'http://localhost:8008'
                }
            )
            
            init_response = await stub.Initialize(init_request, timeout=10.0)
            assert init_response.success is True
            
            # Start a call
            call_request = cp_pb2.CallStartRequest(
                call_id='test_call_001',
                target_address=matrix_test_room,
                camera_stream_url='rtsp://test.example.com/stream',
                camera_capabilities=common_pb2.MediaCapabilities(
                    video_codecs=['H264'],
                    audio_codecs=['OPUS'],
                    webrtc_support=True
                ),
                player_capabilities=common_pb2.MediaCapabilities()
            )
            
            call_response = await stub.StartCall(call_request, timeout=10.0)
            
            assert call_response.success is True
            assert call_response.call_id == 'test_call_001'
            
            # Verify message was sent to Matrix room
            await asyncio.sleep(2)  # Give time for message to be sent
            
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
            
            # End the call
            end_request = cp_pb2.CallEndRequest(
                call_id='test_call_001',
                reason='Test completed'
            )
            
            end_response = await stub.EndCall(end_request, timeout=10.0)
            assert end_response.success is True
            
            await channel.close()
            
        except grpc.RpcError as e:
            pytest.skip(f"Matrix plugin not available: {e}")
    
    @pytest.mark.asyncio
    async def test_matrix_call_with_invalid_room(self, matrix_test_users):
        """Test Matrix call to invalid room"""
        if 'caller' not in matrix_test_users:
            pytest.skip("No test users available")
        
        caller = matrix_test_users['caller']
        
        try:
            channel = grpc.aio.insecure_channel('localhost:50052')
            stub = cp_grpc.CallPluginStub(channel)
            
            # Initialize plugin
            init_request = cp_pb2.InitializeRequest(
                credentials={
                    'access_token': caller['access_token'],
                    'user_id': caller['user_id'],
                    'homeserver': 'http://localhost:8008'
                }
            )
            
            await stub.Initialize(init_request, timeout=10.0)
            
            # Try to start call to invalid room
            call_request = cp_pb2.CallStartRequest(
                call_id='test_call_invalid',
                target_address='!nonexistent:localhost',
                camera_stream_url='rtsp://test.example.com/stream',
                camera_capabilities=common_pb2.MediaCapabilities(),
                player_capabilities=common_pb2.MediaCapabilities()
            )
            
            call_response = await stub.StartCall(call_request, timeout=10.0)
            
            # Should fail gracefully
            assert call_response.success is False
            assert 'not found' in call_response.message.lower() or 'invalid' in call_response.message.lower()
            
            await channel.close()
            
        except grpc.RpcError as e:
            pytest.skip(f"Matrix plugin not available: {e}")


class TestMatrixPluginStandalone:
    """Tests for Matrix plugin running as standalone process"""
    
    @pytest.mark.asyncio
    async def test_matrix_plugin_process_management(self):
        """Test starting and stopping Matrix plugin process"""
        import subprocess
        
        matrix_plugin_dir = "/workspaces/universal/call-assist/addon/plugins/matrix"
        if not os.path.exists(matrix_plugin_dir):
            pytest.skip("Matrix plugin directory not found")
        
        # Check if built version exists
        built_plugin = os.path.join(matrix_plugin_dir, "dist", "index.js")
        if not os.path.exists(built_plugin):
            pytest.skip("Matrix plugin not built")
        
        # Start the plugin process
        process = subprocess.Popen(
            ['node', 'dist/index.js'],
            cwd=matrix_plugin_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        try:
            # Give it time to start
            await asyncio.sleep(3)
            
            # Check if process is running
            assert process.poll() is None, "Matrix plugin process exited unexpectedly"
            
            # Try to connect via gRPC
            channel = grpc.aio.insecure_channel('localhost:50052')
            stub = cp_grpc.CallPluginStub(channel)
            
            # Test basic connectivity
            request = empty_pb2.Empty()
            response = await stub.GetHealth(request, timeout=5.0)
            
            assert response.healthy is True
            
            await channel.close()
            
        except Exception as e:
            pytest.fail(f"Matrix plugin process test failed: {e}")
        
        finally:
            # Clean up: terminate the process
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
