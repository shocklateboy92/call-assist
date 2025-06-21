#!/usr/bin/env python3
"""
Shared test fixtures for Call Assist tests

This module contains broker-related fixtures that are used across multiple test files.
"""

import os
import time
import socket
import logging
import subprocess
import threading

import pytest
import pytest_asyncio
import pytest_homeassistant_custom_component.common
import pytest_socket
import grpc
import grpc.aio
from google.protobuf import empty_pb2

# Test imports
import proto_gen.broker_integration_pb2_grpc as bi_grpc

# Set up logging for tests
logger = logging.getLogger(__name__)


@pytest.fixture()
def enable_socket():
    """Work-around pytest-socket to allow network requests in E2E tests"""
    socket.socket = pytest_socket._true_socket
    socket.socket.connect = pytest_socket._true_connect


def is_port_available(port: int) -> bool:
    """Check if a port is available for binding"""
    # Work-around pytest-socket to allow network requests in E2E tests
    socket.socket = pytest_socket._true_socket
    socket.socket.connect = pytest_socket._true_connect

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('localhost', port))
            return True
        except OSError:
            return False


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
    process = subprocess.Popen([
        "python", broker_script
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=broker_dir)
    
    # Start log streaming thread
    log_thread = threading.Thread(
        target=_stream_broker_logs,
        args=(process, logger),
        daemon=True,
        name="BrokerLogStreamer"
    )
    log_thread.start()
    logger.debug("Started broker log streaming thread")
    
    # Wait for server to start
    max_retries = 20
    for _ in range(max_retries):
        if not is_port_available(broker_port):
            break
        time.sleep(0.5)
    else:
        if process:
            process.terminate()
            process.wait()
        raise RuntimeError("Broker server failed to start within timeout")
    
    logger.info("Broker subprocess started (PID: %d)", process.pid)
    
    yield process
    
    # Cleanup
    if process:
        logger.info("Shutting down broker subprocess...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        logger.info("Broker subprocess shutdown complete")
        
    # Log thread will automatically end when process terminates (daemon=True)
    if log_thread and log_thread.is_alive():
        logger.debug("Waiting for broker log streaming thread to finish...")
        log_thread.join(timeout=2)


@pytest_asyncio.fixture(scope="function")
async def broker_server(broker_process):
    """Get broker connection for each test"""
    broker_port = 50051
    
    # Create client connection to the session-scoped broker
    channel = grpc.aio.insecure_channel(f'localhost:{broker_port}')
    stub = bi_grpc.BrokerIntegrationStub(channel)
    
    # Verify server is responsive
    from google.protobuf import empty_pb2
    await stub.GetSystemCapabilities(empty_pb2.Empty(), timeout=5.0)
    
    yield stub
    
    # Cleanup just the channel
    await channel.close()

@pytest.fixture
def call_assist_integration(monkeypatch) -> None:
    """Update the Home Assistant configuration directory so the integration can be loaded."""
    monkeypatch.setattr(
        pytest_homeassistant_custom_component.common,
        "get_test_config_dir",
        lambda _add_path="": "/workspaces/universal/call-assist/config/homeassistant",
    )
