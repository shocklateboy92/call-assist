#!/usr/bin/env python3
"""
Shared test fixtures for Call Assist tests

This module contains broker-related fixtures that are used across multiple test files.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import aiohttp

import fixtures.disable_pytest_socket

# Set up logging for tests
logger = logging.getLogger(__name__)


fixtures.disable_pytest_socket.activate()

class WebUITestClient:
    """Test client for interacting with the Call Assist web UI via HTTP requests"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_page(self, path: str) -> tuple[str, BeautifulSoup]:
        """Get a web page and return the HTML content and parsed DOM"""
        if self.session is None:
            raise RuntimeError("Session not initialized")

        url = urljoin(self.base_url, path)
        logger.info(f"GET {url}")

        async with self.session.get(url) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"HTTP {resp.status}: {text}")

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            return html, soup

    async def post_form(
        self, path: str, form_data: Dict[str, Any]
    ) -> tuple[int, str, BeautifulSoup]:
        """Submit a form to the web UI"""
        if self.session is None:
            raise RuntimeError("Session not initialized")

        url = urljoin(self.base_url, path)
        logger.info(f"POST {url} with form data: {list(form_data.keys())}")

        async with self.session.post(url, data=form_data) as resp:
            text = await resp.text()
            soup = BeautifulSoup(text, "html.parser")
            return resp.status, text, soup

    async def wait_for_server(self, max_attempts: int = 30, delay: float = 1.0):
        """Wait for the web server to be ready"""
        for attempt in range(max_attempts):
            try:
                html, soup = await self.get_page("/ui")
                logger.info(f"Server ready after {attempt + 1} attempts")
                return True
            except Exception as e:
                logger.debug(f"Attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
        return False


import os
import socket
import tempfile
import threading
import time

import pytest
import pytest_asyncio

from grpclib.client import Channel
from proto_gen.callassist.broker import BrokerIntegrationStub, HaEntityUpdate
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf

import asyncio
from addon.broker.main import serve



def is_port_available(port: int) -> bool:
    """Check if a port is available for binding"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("localhost", port))
            return True
        except OSError:
            return False


def find_available_port() -> int:
    """Find an available port for binding"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def broker_process():
    """Session-scoped broker running in separate thread"""

    # Create temporary database for testing
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db.close()
    db_path = temp_db.name

    # Find available ports
    grpc_port = find_available_port()
    web_port = find_available_port()

    logger.info(
        f"Starting broker in thread: gRPC={grpc_port}, Web={web_port}, DB={db_path}"
    )

    loop = asyncio.new_event_loop()

    def run_thread():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            serve(grpc_port=grpc_port, web_port=web_port, db_path=db_path)
        )

    # Start broker in separate thread
    broker_thread = threading.Thread(target=run_thread, daemon=True)
    broker_thread.start()

    # Wait for server to start by testing actual gRPC connection
    max_retries = 50  # 5 seconds with 0.1s sleeps
    for _ in range(max_retries):
        try:
            # Test port availability first
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.1)
                result = sock.connect_ex(("localhost", grpc_port))
                if result == 0:
                    logger.info("Broker gRPC port is available")
                    break
        except ConnectionRefusedError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("Broker failed to start within timeout")

    logger.info(f"Broker started in thread on ports gRPC={grpc_port}, Web={web_port}")

    # Return broker info instead of process
    broker_info = {
        "grpc_port": grpc_port,
        "web_port": web_port,
        "db_path": db_path,
        "thread": broker_thread,
    }

    yield broker_info

    # Cleanup
    logger.info("Shutting down broker thread...")
    broker_thread.join(timeout=5.0)

    if broker_thread.is_alive():
        logger.warning("Broker thread did not shut down gracefully")

    # Clean up temporary database
    try:
        os.unlink(db_path)
    except OSError:
        pass

    logger.info("Broker thread shutdown complete")


@pytest_asyncio.fixture(scope="function")
async def broker_server(broker_process):
    """Get broker connection for each test"""

    # Get port from broker process info
    broker_port = broker_process["grpc_port"]

    # Create client connection to the session-scoped broker
    channel = Channel(host="localhost", port=broker_port)
    stub = BrokerIntegrationStub(channel)

    # Verify server is responsive
    await stub.health_check(
        betterproto_lib_pydantic_google_protobuf.Empty(), timeout=5.0
    )

    yield stub

    # Cleanup just the channel
    channel.close()


@pytest.fixture(autouse=True, scope="session")
def setup_integration_path():
    """Set up the integration path for testing."""
    import os
    import sys

    # Set environment variable for custom components path
    os.environ["CUSTOM_COMPONENTS_PATH"] = (
        "/workspaces/universal/call_assist/config/homeassistant/custom_components"
    )

    # Add to Python path
    config_path = "/workspaces/universal/call_assist/config/homeassistant"
    if config_path not in sys.path:
        sys.path.insert(0, config_path)

    # Patch the common module at session level
    import pytest_homeassistant_custom_component.common as common

    original_get_test_config_dir = common.get_test_config_dir

    def patched_get_test_config_dir(*add_path):
        return os.path.join(
            "/workspaces/universal/call_assist/config/homeassistant", *add_path
        )

    common.get_test_config_dir = patched_get_test_config_dir

    yield

    # Cleanup
    common.get_test_config_dir = original_get_test_config_dir
    if config_path in sys.path:
        sys.path.remove(config_path)
    if "CUSTOM_COMPONENTS_PATH" in os.environ:
        del os.environ["CUSTOM_COMPONENTS_PATH"]


@pytest.fixture(autouse=True)
def enable_custom_integrations_fixture(enable_custom_integrations):
    """Enable custom integrations for each test."""
    yield


@pytest.fixture(scope="session")
def rtsp_test_server() -> str:
    """Reference to RTSP test server running via docker-compose"""
    import socket
    import time

    # Use service name for docker-compose network
    rtsp_host = "rtsp-server"
    rtsp_port = 8554

    logger.info(f"Using RTSP server at {rtsp_host}:{rtsp_port}")
    return f"rtsp://{rtsp_host}:{rtsp_port}"


@pytest.fixture
def mock_cameras(rtsp_test_server: str) -> List[HaEntityUpdate]:
    """Mock Home Assistant camera entities with RTSP test streams"""
    return [
        HaEntityUpdate(
            entity_id="camera.test_front_door",
            domain="camera",
            name="Test Front Door Camera",
            state="streaming",
            attributes={
                "entity_picture": "/api/camera_proxy/camera.test_front_door",
                "supported_features": "1",
                "stream_source": f"{rtsp_test_server}/test_camera_1",
                "brand": "Test Camera",
                "model": "Virtual RTSP v1.0",
                "friendly_name": "Test Front Door Camera",
            },
            available=True,
            last_updated=datetime.now(timezone.utc),
        ),
        HaEntityUpdate(
            entity_id="camera.test_back_yard",
            domain="camera",
            name="Test Back Yard Camera",
            state="streaming",
            attributes={
                "entity_picture": "/api/camera_proxy/camera.test_back_yard",
                "supported_features": "1",
                "stream_source": f"{rtsp_test_server}/test_camera_2",
                "brand": "Test Camera",
                "model": "Virtual RTSP v2.0",
                "friendly_name": "Test Back Yard Camera",
            },
            available=True,
            last_updated=datetime.now(timezone.utc),
        ),
        HaEntityUpdate(
            entity_id="camera.test_kitchen",
            domain="camera",
            name="Test Kitchen Camera",
            state="unavailable",
            attributes={
                "entity_picture": "/api/camera_proxy/camera.test_kitchen",
                "supported_features": "1",
                "stream_source": f"{rtsp_test_server}/test_camera_offline",
                "brand": "Test Camera",
                "model": "Virtual RTSP v1.0",
                "friendly_name": "Test Kitchen Camera",
            },
            available=False,
            last_updated=datetime.now(timezone.utc),
        ),
    ]


@pytest.fixture
def mock_media_players() -> List[HaEntityUpdate]:
    """Mock Home Assistant media player entities that simulate Chromecast behavior"""
    return [
        HaEntityUpdate(
            entity_id="media_player.test_living_room_tv",
            domain="media_player",
            name="Test Living Room TV",
            state="idle",
            attributes={
                "supported_features": "152463",  # Cast-compatible features
                "device_class": "tv",
                "friendly_name": "Test Living Room TV",
                "volume_level": "0.5",
                "media_content_type": "",
                "media_title": "",
            },
            available=True,
            last_updated=datetime.now(timezone.utc),
        ),
        HaEntityUpdate(
            entity_id="media_player.test_kitchen_display",
            domain="media_player",
            name="Test Kitchen Display",
            state="idle",
            attributes={
                "supported_features": "152463",
                "device_class": "speaker",
                "friendly_name": "Test Kitchen Display",
                "volume_level": "0.7",
                "media_content_type": "",
                "media_title": "",
            },
            available=True,
            last_updated=datetime.now(timezone.utc),
        ),
        HaEntityUpdate(
            entity_id="media_player.test_bedroom_speaker",
            domain="media_player",
            name="Test Bedroom Speaker",
            state="unavailable",
            attributes={
                "supported_features": "152463",
                "device_class": "speaker",
                "friendly_name": "Test Bedroom Speaker",
                "volume_level": "0.3",
                "media_content_type": "",
                "media_title": "",
            },
            available=False,
            last_updated=datetime.now(timezone.utc),
        ),
    ]


@pytest.fixture
def video_test_environment(
    rtsp_test_server: str,
    mock_cameras: List[HaEntityUpdate],
    mock_media_players: List[HaEntityUpdate],
):
    """Complete video testing environment with all components"""
    import socket
    import time

    # Use service name for docker-compose network
    chromecast_host = "mock-chromecast"
    chromecast_port = 8008

    logger.info(f"Using mock Chromecast at {chromecast_host}:{chromecast_port}")

    return {
        "rtsp_base_url": rtsp_test_server,
        "rtsp_streams": [
            f"{rtsp_test_server}/test_camera_1",
            f"{rtsp_test_server}/test_camera_2",
        ],
        "cameras": mock_cameras,
        "media_players": mock_media_players,
        "mock_chromecast_url": f"http://{chromecast_host}:{chromecast_port}",
    }


@pytest_asyncio.fixture
async def web_ui_client(broker_process):
    """Web UI test client configured for the running broker"""
    web_port = broker_process["web_port"]
    base_url = f"http://localhost:{web_port}"

    async with WebUITestClient(base_url) as client:
        # Wait for web server to be ready
        ready = await client.wait_for_server(max_attempts=10, delay=0.5)
        if not ready:
            raise RuntimeError("Web UI server failed to start")
        yield client
