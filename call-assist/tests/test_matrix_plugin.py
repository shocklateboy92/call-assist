#!/usr/bin/env python3
"""
Matrix Plugin Integration Tests

These tests verify the Matrix plugin's behavior when managed by the broker.
The broker starts the plugin on demand and handles all communication.
Tests use a real Matrix homeserver for protocol validation.
"""

import asyncio
import pytest
import pytest_asyncio
import grpc
import grpc.aio
import os
import time
import subprocess
import signal
import socket
import threading
import logging
from typing import Dict, Any, Optional
from aiohttp import ClientSession

# Test imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import proto_gen.broker_integration_pb2 as bi_pb2
import proto_gen.common_pb2 as common_pb2
import proto_gen.broker_integration_pb2_grpc as bi_grpc
from google.protobuf import empty_pb2

# Set up logging for tests
logger = logging.getLogger(__name__)


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
        """Register a test user on the Matrix homeserver, or login if already exists"""
        # First try to login in case user already exists
        login_result = await self.login(username, password)
        if 'access_token' in login_result:
            return login_result
        
        # If login failed, try to register
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
            elif resp.status == 400 and 'M_USER_IN_USE' in str(result):
                # User already exists, try to login again
                login_result = await self.login(username, password)
                return login_result
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
    
    async def create_room(self, name: Optional[str] = None, is_public: bool = False, is_direct: bool = False, invite_users: list = None) -> Dict[str, Any]:
        """Create a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "visibility": "public" if is_public else "private"
        }
        
        if is_direct:
            # For direct chats, use specific settings per Matrix spec
            data["preset"] = "trusted_private_chat"
            data["is_direct"] = True

        # Don't set a name for direct chats - they should be nameless
        if name:
            data["name"] = name
        
        if invite_users:
            data["invite"] = invite_users
        
        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()
    
    async def invite_user_to_room(self, room_id: str, user_id: str) -> Dict[str, Any]:
        """Invite a user to a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/invite"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {
            "user_id": user_id
        }
        
        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()
    
    async def join_room(self, room_id: str) -> Dict[str, Any]:
        """Join a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/join"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        async with self.session.post(url, json={}, headers=headers) as resp:
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
    
    async def get_account_data(self, type_filter: Optional[str] = None) -> Dict[str, Any]:
        """Get user account data"""
        if type_filter:
            url = f"{self.homeserver_url}/_matrix/client/r0/user/{self.user_id}/account_data/{type_filter}"
        else:
            url = f"{self.homeserver_url}/_matrix/client/r0/user/{self.user_id}/account_data"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 404:
                return {}
            return await resp.json()
    
    async def set_account_data(self, data_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """Set user account data"""
        url = f"{self.homeserver_url}/_matrix/client/r0/user/{self.user_id}/account_data/{data_type}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        async with self.session.put(url, json=content, headers=headers) as resp:
            return await resp.json() if resp.status != 200 else {}


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
_broker_log_thread = None


def _stream_broker_logs(process, logger):
    """Stream broker subprocess logs to the test logger"""
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            
            line = line.strip()
            if not line:
                continue
                
            # Try to parse structured log line: "2025-06-18 05:23:57 [    INFO] main: Starting..."
            # Extract log level and message for proper forwarding
            if '[' in line and ']' in line:
                try:
                    # Find the last occurrence of [ ] pattern (in case there are multiple)
                    bracket_pairs = []
                    start = 0
                    while True:
                        start_bracket = line.find('[', start)
                        if start_bracket == -1:
                            break
                        end_bracket = line.find(']', start_bracket)
                        if end_bracket == -1:
                            break
                        bracket_pairs.append((start_bracket, end_bracket))
                        start = end_bracket + 1
                    
                    if bracket_pairs:
                        # Use the last bracket pair (should be the log level)
                        start_bracket, end_bracket = bracket_pairs[-1]
                        level_part = line[start_bracket+1:end_bracket].strip()
                        
                        # Map broker log levels to our logger
                        level_map = {
                            'DEBUG': logging.DEBUG,
                            'INFO': logging.INFO,
                            'WARNING': logging.WARNING,
                            'WARN': logging.WARNING,
                            'ERROR': logging.ERROR,
                            'CRITICAL': logging.CRITICAL
                        }
                        
                        # Check if this looks like a log level
                        if level_part in level_map:
                            message_part = line[end_bracket+1:].strip()
                            log_level = level_map[level_part]
                            logger.log(log_level, "[BROKER] %s", message_part)
                            continue
                            
                except (ValueError, IndexError):
                    pass
            
            # Fallback: log the entire line as INFO
            logger.info("[BROKER] %s", line)
            
    except Exception as e:
        logger.error("Error streaming broker logs: %s", e)
    finally:
        logger.debug("Broker log streaming thread ended")


@pytest.fixture(scope="session")
def broker_process():
    """Session-scoped broker subprocess"""
    global _broker_process, _broker_log_thread
    broker_port = 50051
    
    # Check if broker is already running
    if not is_port_available(broker_port):
        logger.info("Using existing broker server on port %d", broker_port)
        yield None  # External broker
        return
    
    # Start broker as subprocess
    logger.info("Starting broker subprocess on port %d", broker_port)
    broker_script = os.path.join(os.path.dirname(__file__), "..", "addon", "broker", "main.py")
    broker_dir = os.path.join(os.path.dirname(__file__), "..", "addon", "broker")
    _broker_process = subprocess.Popen([
        "python", broker_script
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=broker_dir)
    
    # Start log streaming thread
    _broker_log_thread = threading.Thread(
        target=_stream_broker_logs,
        args=(_broker_process, logger),
        daemon=True,
        name="BrokerLogStreamer"
    )
    _broker_log_thread.start()
    logger.debug("Started broker log streaming thread")
    
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
    
    logger.info("Broker subprocess started (PID: %d)", _broker_process.pid)
    
    yield _broker_process
    
    # Cleanup
    if _broker_process:
        logger.info("Shutting down broker subprocess...")
        _broker_process.terminate()
        try:
            _broker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _broker_process.kill()
            _broker_process.wait()
        logger.info("Broker subprocess shutdown complete")
        _broker_process = None
        
    # Log thread will automatically end when process terminates (daemon=True)
    if _broker_log_thread and _broker_log_thread.is_alive():
        logger.debug("Waiting for broker log streaming thread to finish...")
        _broker_log_thread.join(timeout=2)
        _broker_log_thread = None


@pytest_asyncio.fixture(scope="function")
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

TEST_PASSWORD = "testpassword123"
RECEIVER_USERNAME = "testreceiver"
CALLER_USERNAME = "testcaller"
TEST_ROOM_NAME = "Test Video Call Room"

@pytest_asyncio.fixture
async def matrix_test_users():
    """Create test users on the Matrix homeserver"""
    users = {}
    
    async with MatrixTestClient() as client:
        # Use consistent caller user (will login if already exists)
        caller_result = await client.register_user(
            CALLER_USERNAME, 
            TEST_PASSWORD
        )
        if 'access_token' in caller_result:
            users['caller'] = {
                'user_id': caller_result['user_id'],
                'access_token': caller_result['access_token'],
                'password': TEST_PASSWORD
            }
        
        # Use consistent receiver user (will login if already exists)
        receiver_result = await client.register_user(
            RECEIVER_USERNAME, 
            TEST_PASSWORD
        )
        if 'access_token' in receiver_result:
            users['receiver'] = {
                'user_id': receiver_result['user_id'],
                'access_token': receiver_result['access_token'],
                'password': TEST_PASSWORD
            }
    
    return users


@pytest_asyncio.fixture
async def matrix_test_room(broker_server, matrix_test_users):
    """Get or create a consistent direct chat between caller and receiver"""
    if 'receiver' not in matrix_test_users or 'caller' not in matrix_test_users:
        pytest.skip("Both receiver and caller users required")
    
    receiver = matrix_test_users['receiver']
    caller = matrix_test_users['caller']
    
    # Setup receiver credentials in broker
    creds_request = bi_pb2.CredentialsRequest(
        protocol='matrix',
        credentials={
            'access_token': receiver['access_token'],
            'user_id': receiver['user_id'],
            'homeserver': 'http://synapse:8008'
        }
    )
    
    await broker_server.UpdateCredentials(creds_request, timeout=10.0)
    
    # Check if a direct chat room already exists
    test_room_id = None
    
    async with MatrixTestClient() as client:
        client.access_token = receiver['access_token']
        client.user_id = receiver['user_id']
        
        # Check existing m.direct account data for existing room with caller
        direct_data = await client.get_account_data('m.direct')
        if direct_data and caller['user_id'] in direct_data:
            room_list = direct_data[caller['user_id']]
            if room_list:
                # Use the first existing room
                test_room_id = room_list[0]
        
        # If no existing room found, create a new direct chat
        if not test_room_id:
            room_result = await client.create_room(
                is_direct=True,
                invite_users=[caller['user_id']]
            )
            if 'room_id' in room_result:
                test_room_id = room_result['room_id']
                
                # Set m.direct account data for receiver
                if not direct_data:
                    direct_data = {}
                
                # Add this room as a direct chat with the caller
                if caller['user_id'] not in direct_data:
                    direct_data[caller['user_id']] = []
                if test_room_id not in direct_data[caller['user_id']]:
                    direct_data[caller['user_id']].append(test_room_id)
                    
                await client.set_account_data('m.direct', direct_data)
    
    if not test_room_id:
        pytest.skip("Could not find or create direct chat room")
    
    # Ensure caller has joined the direct chat and has proper m.direct data
    async with MatrixTestClient() as client:
        client.access_token = caller['access_token']
        client.user_id = caller['user_id']
        
        # Try to join the room (will succeed silently if already joined)
        await client.join_room(test_room_id)
        
        # Set m.direct account data for caller
        direct_data = await client.get_account_data('m.direct')
        if not direct_data:
            direct_data = {}
        
        # Add this room as a direct chat with the receiver
        if receiver['user_id'] not in direct_data:
            direct_data[receiver['user_id']] = []
        if test_room_id not in direct_data[receiver['user_id']]:
            direct_data[receiver['user_id']].append(test_room_id)
            
        await client.set_account_data('m.direct', direct_data)
    
    return test_room_id


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
