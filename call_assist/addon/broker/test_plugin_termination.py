#!/usr/bin/env python3

import asyncio
import logging
import signal
import tempfile
from typing import Any
from unittest.mock import Mock, patch

from addon.broker.plugin_manager import (
    CapabilitiesConfig,
    ExecutableConfig,
    GrpcConfig,
    PluginInstance,
    PluginManager,
    PluginMetadata,
    PluginState,
    ResolutionConfig,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_emergency_cleanup() -> None:
    """Test emergency cleanup functionality"""

    with tempfile.TemporaryDirectory() as temp_dir:
        pm = PluginManager(plugins_root=temp_dir)

        # Create a mock plugin with a mock process
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process is still running
        mock_process.pid = 12345
        mock_process.terminate.return_value = None
        mock_process.wait.return_value = None
        mock_process.kill.return_value = None

        # Add a mock plugin instance
        plugin = PluginInstance(
            metadata=PluginMetadata(
                name="Test Plugin",
                protocol="test",
                executable=ExecutableConfig(type="node", command=["node", "test.js"]),
                grpc=GrpcConfig(port=50052),
                capabilities=CapabilitiesConfig(
                    video_codecs=["VP8"],
                    audio_codecs=["OPUS"],
                    supported_resolutions=[ResolutionConfig(width=640, height=480, framerate=30)],
                    webrtc_support=True
                )
            ),
            plugin_dir="/tmp/test",
            process=mock_process,
            state=PluginState.RUNNING
        )

        pm.plugins["test"] = plugin

        # Test emergency cleanup
        pm._emergency_cleanup()

        # Verify the process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called()

        # Verify shutdown flag was set
        assert pm._shutdown_requested is True

        logger.info("✅ Emergency cleanup test passed")


def test_signal_handler() -> None:
    """Test signal handler registration and basic functionality"""

    with tempfile.TemporaryDirectory() as temp_dir:
        pm = PluginManager(plugins_root=temp_dir)

        # Verify signal handlers were registered
        assert signal.signal(signal.SIGTERM, signal.SIG_DFL) == pm._signal_handler
        assert signal.signal(signal.SIGINT, signal.SIG_DFL) == pm._signal_handler

        # Reset signal handlers
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        logger.info("✅ Signal handler registration test passed")


async def test_graceful_shutdown() -> None:
    """Test graceful shutdown with timeout"""

    with tempfile.TemporaryDirectory() as temp_dir:
        pm = PluginManager(plugins_root=temp_dir)

        # Create a mock plugin
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345

        plugin = PluginInstance(
            metadata=PluginMetadata(
                name="Test Plugin",
                protocol="test",
                executable=ExecutableConfig(type="node", command=["node", "test.js"]),
                grpc=GrpcConfig(port=50052),
                capabilities=CapabilitiesConfig(
                    video_codecs=["VP8"],
                    audio_codecs=["OPUS"],
                    supported_resolutions=[ResolutionConfig(width=640, height=480, framerate=30)],
                    webrtc_support=True
                )
            ),
            plugin_dir="/tmp/test",
            process=mock_process,
            state=PluginState.RUNNING
        )

        pm.plugins["test"] = plugin

        # Mock the _stop_plugin method to simulate timeout
        async def mock_stop_plugin(_) -> None:
            await asyncio.sleep(15)  # Longer than timeout

        with patch.object(pm, '_stop_plugin', side_effect=mock_stop_plugin):
            # Test shutdown with timeout
            await pm.shutdown_all()

        # Should have completed despite timeout
        assert pm._shutdown_requested is True

        logger.info("✅ Graceful shutdown with timeout test passed")


if __name__ == "__main__":
    logger.info("Starting plugin termination tests...")

    test_emergency_cleanup()
    test_signal_handler()

    # Run async test
    asyncio.run(test_graceful_shutdown())

    logger.info("🎉 All plugin termination tests passed!")
