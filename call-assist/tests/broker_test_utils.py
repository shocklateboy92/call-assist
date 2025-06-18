#!/usr/bin/env python3

"""
Shared utilities for Call Assist broker testing.

This module provides utilities for:
1. Starting/stopping broker processes
2. Managing broker connections
3. Checking port availability
4. Streaming broker logs

Extracted from the original Matrix plugin tests.
"""

import asyncio
import logging
import os
import socket
import subprocess
import threading
import time
from typing import Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import grpc.aio
import proto_gen.broker_integration_pb2_grpc as bi_grpc
from google.protobuf import empty_pb2

logger = logging.getLogger(__name__)


def is_port_available(port: int, host: str = 'localhost') -> bool:
    """Check if a port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _stream_broker_logs(process, log_handler):
    """Stream broker subprocess logs to the provided logger."""
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
                            log_handler.log(log_level, "[BROKER] %s", message_part)
                            continue
                            
                except (ValueError, IndexError):
                    pass
            
            # Fallback: log the entire line as INFO
            log_handler.info("[BROKER] %s", line)
            
    except Exception as e:
        log_handler.error("Error streaming broker logs: %s", e)
    finally:
        log_handler.debug("Broker log streaming thread ended")


class BrokerManager:
    """Manages Call Assist broker process lifecycle."""
    
    def __init__(self, port: int = 50051, broker_script_path: Optional[str] = None):
        self.port = port
        self.broker_script_path = broker_script_path or self._find_broker_script()
        self.process: Optional[subprocess.Popen] = None
        self.log_thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger(f"{__name__}.BrokerManager")
    
    def _find_broker_script(self) -> str:
        """Find the broker main.py script."""
        # Try relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try parent directory structure
        candidates = [
            os.path.join(current_dir, '..', 'addon', 'broker', 'main.py'),
            os.path.join(current_dir, '..', '..', 'call-assist', 'addon', 'broker', 'main.py'),
            '/workspaces/universal/call-assist/addon/broker/main.py',
        ]
        
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        
        raise FileNotFoundError("Could not find broker main.py script")
    
    def is_running(self) -> bool:
        """Check if broker is running (either our process or external)."""
        return not is_port_available(self.port)
    
    def start(self, timeout: float = 10.0) -> bool:
        """Start broker process if not already running."""
        if self.is_running():
            self.logger.info("Broker already running on port %d", self.port)
            return True
        
        self.logger.info("Starting broker subprocess on port %d", self.port)
        
        try:
            self.process = subprocess.Popen([
                "python", self.broker_script_path
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            # Start log streaming thread
            self.log_thread = threading.Thread(
                target=_stream_broker_logs,
                args=(self.process, self.logger),
                daemon=True,
                name="BrokerLogStreamer"
            )
            self.log_thread.start()
            self.logger.debug("Started broker log streaming thread")
            
            # Wait for server to start
            max_retries = int(timeout * 2)  # Check every 0.5 seconds
            for _ in range(max_retries):
                if self.is_running():
                    self.logger.info("Broker subprocess started (PID: %d)", self.process.pid)
                    return True
                time.sleep(0.5)
            
            # Startup failed
            self.logger.error("Broker failed to start within %.1f seconds", timeout)
            self.stop()
            return False
            
        except Exception as ex:
            self.logger.error("Failed to start broker: %s", ex)
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop broker process if we started it."""
        if self.process:
            self.logger.info("Shutting down broker subprocess...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.logger.warning("Broker didn't terminate gracefully, killing...")
                self.process.kill()
                self.process.wait()
            
            self.logger.info("Broker subprocess shutdown complete")
            self.process = None
        
        # Log thread will automatically end when process terminates (daemon=True)
        if self.log_thread and self.log_thread.is_alive():
            self.logger.debug("Waiting for broker log streaming thread to finish...")
            self.log_thread.join(timeout=2)
            self.log_thread = None
    
    def __enter__(self):
        """Context manager entry."""
        if not self.start():
            raise RuntimeError("Failed to start broker")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class BrokerClient:
    """Async client for connecting to Call Assist broker."""
    
    def __init__(self, host: str = 'localhost', port: int = 50051):
        self.host = host
        self.port = port
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[bi_grpc.BrokerIntegrationStub] = None
    
    async def connect(self, timeout: float = 5.0) -> bool:
        """Connect to broker."""
        try:
            self.channel = grpc.aio.insecure_channel(f'{self.host}:{self.port}')
            self.stub = bi_grpc.BrokerIntegrationStub(self.channel)
            
            # Verify server is responsive
            await self.stub.GetSystemCapabilities(empty_pb2.Empty(), timeout=timeout)
            return True
            
        except Exception as ex:
            logger.error("Failed to connect to broker: %s", ex)
            await self.disconnect()
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from broker."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        if not await self.connect():
            raise RuntimeError("Failed to connect to broker")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Global broker manager for session-level management
_global_broker_manager: Optional[BrokerManager] = None


def get_or_start_broker(port: int = 50051) -> BrokerManager:
    """Get global broker manager, starting broker if needed."""
    global _global_broker_manager
    
    if _global_broker_manager is None:
        _global_broker_manager = BrokerManager(port=port)
    
    if not _global_broker_manager.is_running():
        if not _global_broker_manager.start():
            raise RuntimeError("Failed to start broker")
    
    return _global_broker_manager


def stop_global_broker() -> None:
    """Stop global broker if running."""
    global _global_broker_manager
    
    if _global_broker_manager:
        _global_broker_manager.stop()
        _global_broker_manager = None