#!/usr/bin/env python3
"""
Shared test fixtures for Call Assist tests

This module contains broker-related fixtures that are used across multiple test files.
"""

import asyncio
import contextlib
import logging
import os
import socket
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from types import TracebackType
from urllib.parse import urljoin

import aiohttp
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf
import pytest
from bs4 import BeautifulSoup, Tag
from grpclib.client import Channel

from addon.broker.main import serve
from proto_gen.callassist.broker import (
    BrokerIntegrationStub,
    HaEntityUpdate,
)

from .types import (
    BrokerProcessInfo,
    CustomIntegrationsFixture,
    VideoTestEnvironment,
)

logger = logging.getLogger(__name__)


class WebUITestClient(contextlib.AbstractAsyncContextManager["WebUITestClient", None]):
    """Test client for interacting with the Call Assist web UI via HTTP requests"""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "WebUITestClient":
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback  # Mark as intentionally unused
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
        self, path: str, form_data: dict[str, object]
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

    async def wait_for_server(self, max_attempts: int = 30, delay: float = 1.0) -> bool:
        """Wait for the web server to be ready"""
        for attempt in range(max_attempts):
            try:
                _ = await self.get_page("/ui")
                logger.info(f"Server ready after {attempt + 1} attempts")
                return True
            except ConnectionError as e:
                logger.debug(f"Attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
        return False

    def extract_accounts_from_table(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        """Extract account information from the accounts table in the UI"""
        accounts = []

        # First validate that we have proper HTML structure
        body = soup.find("body")
        if isinstance(body, Tag) and "children" in body.attrs:
            # This indicates malformed HTML where server sent string as attribute
            raise AssertionError(
                "Malformed HTML detected: body tag has 'children' attribute instead of proper child elements"
            )

        # Look for table rows in the accounts table
        table_rows = soup.find_all("tr")

        for row in table_rows:
            if isinstance(row, Tag):
                cells = row.find_all("td")
                if (
                    len(cells) >= 5
                ):  # protocol, account_id, display_name, status, updated, actions
                    account = {
                        "protocol": cells[0].get_text(strip=True).lower(),
                        "account_id": cells[1].get_text(strip=True),
                        "display_name": cells[2].get_text(strip=True),
                        "status": cells[3].get_text(strip=True),
                        "updated": cells[4].get_text(strip=True),
                    }
                    accounts.append(account)

        # Filter out header row and empty rows
        return [
            acc for acc in accounts if acc["protocol"] and acc["protocol"] != "protocol"
        ]

    def extract_protocol_options(self, soup: BeautifulSoup) -> list[str]:
        """Extract available protocols from a protocol selection dropdown"""
        protocols = []

        # Look for select options (skip empty/placeholder options)
        options = soup.find_all("option")
        for option in options:
            if isinstance(option, Tag):
                value = option.get("value")
                if value and isinstance(value, str) and value.strip() and value != "":
                    protocols.append(value.strip())

        return protocols

    def find_form_inputs(self, soup: BeautifulSoup) -> dict[str, str]:
        """Find all form input fields and their names/types"""
        inputs = {}

        # Find input elements
        for input_elem in soup.find_all("input"):
            if isinstance(input_elem, Tag):
                name = input_elem.get("name")
                input_type = input_elem.get("type", "text")
                if name and isinstance(name, str):
                    inputs[name] = str(input_type) if input_type else "text"

        # Find select elements
        for select_elem in soup.find_all("select"):
            if isinstance(select_elem, Tag):
                name = select_elem.get("name")
                if name and isinstance(name, str):
                    inputs[name] = "select"

        # Find textarea elements
        for textarea_elem in soup.find_all("textarea"):
            if isinstance(textarea_elem, Tag):
                name = textarea_elem.get("name")
                if name and isinstance(name, str):
                    inputs[name] = "textarea"

        return inputs

    def validate_html_structure(
        self, soup: BeautifulSoup, page_name: str = "page"
    ) -> None:
        """Validate that the HTML structure is properly formed and not malformed by server errors"""
        # Check for malformed body tag with string content as attribute
        body = soup.find("body")
        if not isinstance(body, Tag):
            raise AssertionError(
                f"Malformed HTML in {page_name}: body tag not found or not a valid Tag"
            )
        # Type checker now knows body is a Tag

        if "children" in body.attrs:
            raise AssertionError(
                f"Malformed HTML in {page_name}: body tag has 'children' attribute containing string content instead of proper child elements"
            )

        # Body should have actual HTML child elements, not just raw text
        child_elements = body.find_all(recursive=False)  # Direct children only
        if len(child_elements) == 0:
            # Check if body only contains text (which might indicate serialization error)
            body_text = body.get_text(strip=True)
            if (
                body_text and len(body_text) > 100
            ):  # Suspiciously long text without structure
                raise AssertionError(
                    f"Malformed HTML in {page_name}: body contains only text content without proper HTML structure"
                )

        # Check for common error patterns in the HTML
        html_text = str(soup).lower()
        error_patterns = [
            "children=",  # Ludic serialization error
            "internal server error",
            "500 internal server error",
            "traceback",
            "exception occurred",
        ]

        for pattern in error_patterns:
            if pattern in html_text:
                raise AssertionError(
                    f"HTML structure error in {page_name}: found error pattern '{pattern}'"
                )

    def extract_visible_text_content(self, soup: BeautifulSoup) -> str:
        """Extract all user-visible text from the page for content validation"""
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text content and clean it up
        text = soup.get_text()
        # Normalize whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return " ".join(chunk for chunk in chunks if chunk)



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
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def broker_process() -> Iterator[BrokerProcessInfo]:
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

    server_task: asyncio.Task[None] | None = None

    def run_thread() -> None:
        nonlocal server_task
        asyncio.set_event_loop(loop)
        server_task = loop.create_task(
            serve(grpc_port=grpc_port, web_port=web_port, db_path=db_path)
        )
        loop.run_until_complete(server_task)

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
    broker_info = BrokerProcessInfo(
        grpc_port=grpc_port,
        web_port=web_port,
        db_path=db_path,
        thread=broker_thread,
    )

    yield broker_info

    # Cancelling the current task should shut down the broker gracefully
    if server_task:
        logger.info("Cancelling broker task...")
        server_task.cancel()

    # Cleanup
    logger.info("Shutting down broker thread...")
    broker_thread.join(timeout=5.0)

    if broker_thread.is_alive():
        logger.warning("Broker thread did not shut down gracefully")

    # Clean up temporary database
    with contextlib.suppress(OSError):
        os.unlink(db_path)

    logger.info("Broker thread shutdown complete")


@pytest.fixture(scope="function")
async def broker_server(
    broker_process: BrokerProcessInfo,
) -> AsyncIterator[BrokerIntegrationStub]:
    """Get broker connection for each test"""

    # Get port from broker process info
    broker_port = broker_process.grpc_port

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
def setup_integration_path() -> Iterator[None]:
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

    def patched_get_test_config_dir(*add_path: str) -> str:
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
def enable_custom_integrations_fixture(
    enable_custom_integrations: CustomIntegrationsFixture,
) -> Iterator[None]:
    """Enable custom integrations for each test."""
    _ = enable_custom_integrations  # Use the parameter to avoid unused warning
    yield


@pytest.fixture(scope="session")
def rtsp_test_server() -> str:
    """Reference to RTSP test server running via docker-compose"""
    # Use service name for docker-compose network
    rtsp_host = "rtsp-server"
    rtsp_port = 8554

    logger.info(f"Using RTSP server at {rtsp_host}:{rtsp_port}")
    return f"rtsp://{rtsp_host}:{rtsp_port}"


@pytest.fixture
def mock_cameras(rtsp_test_server: str) -> list[HaEntityUpdate]:
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
            last_updated=datetime.now(UTC),
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
            last_updated=datetime.now(UTC),
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
            last_updated=datetime.now(UTC),
        ),
    ]


@pytest.fixture
def mock_media_players() -> list[HaEntityUpdate]:
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
            last_updated=datetime.now(UTC),
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
            last_updated=datetime.now(UTC),
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
            last_updated=datetime.now(UTC),
        ),
    ]


@pytest.fixture
def video_test_environment(
    rtsp_test_server: str,
    mock_cameras: list[HaEntityUpdate],
    mock_media_players: list[HaEntityUpdate],
) -> VideoTestEnvironment:
    """Complete video testing environment with all components"""
    # Use service name for docker-compose network
    chromecast_host = "mock-chromecast"
    chromecast_port = 8008

    logger.info(f"Using mock Chromecast at {chromecast_host}:{chromecast_port}")

    return VideoTestEnvironment(
        rtsp_base_url=rtsp_test_server,
        rtsp_streams=[
            f"{rtsp_test_server}/test_camera_1",
            f"{rtsp_test_server}/test_camera_2",
        ],
        cameras=mock_cameras,
        media_players=mock_media_players,
        mock_chromecast_url=f"http://{chromecast_host}:{chromecast_port}",
    )


@pytest.fixture
async def web_ui_client(
    broker_process: BrokerProcessInfo,
) -> AsyncIterator[WebUITestClient]:
    """Web UI test client configured for the running broker"""
    web_port = broker_process.web_port
    base_url = f"http://localhost:{web_port}"

    async with WebUITestClient(base_url) as client:
        # Wait for web server to be ready
        ready = await client.wait_for_server(max_attempts=10, delay=0.5)
        if not ready:
            raise RuntimeError("Web UI server failed to start")
        yield client
