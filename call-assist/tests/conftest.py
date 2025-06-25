#!/usr/bin/env python3
"""
Shared test fixtures for Call Assist tests

This module contains broker-related fixtures that are used across multiple test files.
"""

import logging

# Set up logging for tests
logger = logging.getLogger(__name__)

import pytest_socket


def stub_method(*args, **kwargs):
    """Stub method to disable pytest-socket"""
    logger.info(
        "pytest-socket disabled. These are integration tests that require network access."
    )
    pass


pytest_socket.disable_socket = stub_method

import os
import socket
import tempfile
import threading
import time

import pytest
import pytest_asyncio

from grpclib.client import Channel
from proto_gen.callassist.broker import BrokerIntegrationStub
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf

import asyncio
from addon.broker.main import serve


@pytest.fixture()
def enable_socket():
    """Work-around pytest-socket to allow network requests in E2E tests"""
    _enable_socket()


def _enable_socket():
    socket.socket = pytest_socket._true_socket
    socket.socket.connect = pytest_socket._true_connect


def is_port_available(port: int) -> bool:
    """Check if a port is available for binding"""
    # Work-around pytest-socket to allow network requests in E2E tests
    socket.socket = pytest_socket._true_socket
    socket.socket.connect = pytest_socket._true_connect

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("localhost", port))
            return True
        except OSError:
            return False


def find_available_port() -> int:
    """Find an available port for binding"""
    # Work-around pytest-socket to allow network requests
    socket.socket = pytest_socket._true_socket
    socket.socket.connect = pytest_socket._true_connect

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def broker_process():
    """Session-scoped broker running in separate thread"""

    # Ensure sockets are enabled for broker operations
    _enable_socket()

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

    # Ensure sockets are enabled for broker operations
    _enable_socket()

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
        "/workspaces/universal/call-assist/config/homeassistant/custom_components"
    )

    # Add to Python path
    config_path = "/workspaces/universal/call-assist/config/homeassistant"
    if config_path not in sys.path:
        sys.path.insert(0, config_path)

    # Patch the common module at session level
    import pytest_homeassistant_custom_component.common as common

    original_get_test_config_dir = common.get_test_config_dir

    def patched_get_test_config_dir(*add_path):
        return os.path.join(
            "/workspaces/universal/call-assist/config/homeassistant", *add_path
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
    # Enable sockets for tests that need to connect to broker
    _enable_socket()
    yield
