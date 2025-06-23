#!/usr/bin/env python3
"""
Shared test fixtures for Call Assist tests

This module contains broker-related fixtures that are used across multiple test files.
"""

import os
import socket
import logging
import asyncio
import tempfile

import pytest
import pytest_asyncio
import pytest_homeassistant_custom_component.common
import pytest_socket
from grpclib.client import Channel

# Test imports - updated for betterproto
from proto_gen.callassist.broker import BrokerIntegrationStub
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf

# Set up logging for tests
logger = logging.getLogger(__name__)


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


@pytest_asyncio.fixture(scope="session")
async def broker_process():
    """Session-scoped in-process broker"""

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
        f"Starting in-process broker: gRPC={grpc_port}, Web={web_port}, DB={db_path}"
    )

    # Import broker serve function directly
    from addon.broker.main import serve

    # Start broker in background task
    server_task = asyncio.create_task(
        serve(
            grpc_host="localhost",
            grpc_port=grpc_port,
            web_host="localhost",
            web_port=web_port,
            db_path=db_path,
        )
    )

    # Wait for server to start
    max_retries = 20
    for _ in range(max_retries):
        if not is_port_available(grpc_port):
            break
        await asyncio.sleep(0.1)
    else:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        raise RuntimeError("Broker server failed to start within timeout")

    logger.info(f"In-process broker started on ports gRPC={grpc_port}, Web={web_port}")

    # Return broker info instead of process
    broker_info = {
        "grpc_port": grpc_port,
        "web_port": web_port,
        "db_path": db_path,
        "task": server_task,
    }

    yield broker_info

    # Cleanup
    logger.info("Shutting down in-process broker...")
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass

    # Clean up temporary database
    try:
        os.unlink(db_path)
    except OSError:
        pass

    logger.info("In-process broker shutdown complete")


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
    await stub.get_system_capabilities(
        betterproto_lib_pydantic_google_protobuf.Empty(), timeout=5.0
    )

    yield stub

    # Cleanup just the channel
    channel.close()


@pytest.fixture
def call_assist_integration(monkeypatch) -> None:
    """Update the Home Assistant configuration directory so the integration can be loaded."""
    monkeypatch.setattr(
        pytest_homeassistant_custom_component.common,
        "get_test_config_dir",
        lambda: "/workspaces/universal/call-assist/config/homeassistant",
    )
