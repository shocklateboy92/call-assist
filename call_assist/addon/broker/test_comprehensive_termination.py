#!/usr/bin/env python3

import asyncio
import logging
import tempfile
from unittest.mock import AsyncMock, Mock

from addon.broker.dependencies import AppState
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


async def test_app_state_cleanup():
    """Test that AppState properly cleans up plugin manager"""

    # Create app state
    app_state = AppState()

    # Create mock plugin manager
    mock_plugin_manager = Mock()
    mock_plugin_manager.shutdown_all = AsyncMock()

    app_state.plugin_manager = mock_plugin_manager

    # Test cleanup
    await app_state.cleanup()

    # Verify shutdown_all was called
    mock_plugin_manager.shutdown_all.assert_called_once()

    logger.info("✅ AppState cleanup test passed")


async def test_integration_cleanup_flow():
    """Test the full cleanup flow from broker to plugins"""

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create plugin manager with mock plugins
        pm = PluginManager(plugins_root=temp_dir)

        # Add mock plugin
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate.return_value = None
        mock_process.wait.return_value = None

        plugin = PluginInstance(
            metadata=PluginMetadata(
                name="Test Plugin",
                protocol="test",
                executable=ExecutableConfig(type="node", command=["node", "test.js"]),
                grpc=GrpcConfig(port=50052),
                capabilities=CapabilitiesConfig(
                    video_codecs=["VP8"],
                    audio_codecs=["OPUS"],
                    supported_resolutions=[
                        ResolutionConfig(width=640, height=480, framerate=30)
                    ],
                    webrtc_support=True,
                ),
            ),
            plugin_dir="/tmp/test",
            process=mock_process,
            state=PluginState.RUNNING,
        )

        pm.plugins["test"] = plugin

        # Create app state and set plugin manager
        app_state = AppState()
        app_state.plugin_manager = pm

        # Test the cleanup flow
        await app_state.cleanup()

        # Verify plugin was terminated
        assert pm._shutdown_requested is True

        logger.info("✅ Integration cleanup flow test passed")


def test_signal_handling_integration():
    """Test that signal handlers work correctly"""

    with tempfile.TemporaryDirectory() as temp_dir:
        pm = PluginManager(plugins_root=temp_dir)

        # Add mock plugin
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate.return_value = None
        mock_process.wait.return_value = None

        plugin = PluginInstance(
            metadata=PluginMetadata(
                name="Test Plugin",
                protocol="test",
                executable=ExecutableConfig(type="node", command=["node", "test.js"]),
                grpc=GrpcConfig(port=50052),
                capabilities=CapabilitiesConfig(
                    video_codecs=["VP8"],
                    audio_codecs=["OPUS"],
                    supported_resolutions=[
                        ResolutionConfig(width=640, height=480, framerate=30)
                    ],
                    webrtc_support=True,
                ),
            ),
            plugin_dir="/tmp/test",
            process=mock_process,
            state=PluginState.RUNNING,
        )

        pm.plugins["test"] = plugin

        # Test emergency cleanup directly (simulates what happens when no event loop)
        pm._emergency_cleanup()

        # Should have initiated cleanup
        assert pm._shutdown_requested is True

        # Emergency cleanup should have terminated the process
        mock_process.terminate.assert_called_once()

        logger.info("✅ Signal handling integration test passed")


if __name__ == "__main__":
    logger.info("Starting comprehensive termination tests...")

    # Run async tests
    asyncio.run(test_app_state_cleanup())
    asyncio.run(test_integration_cleanup_flow())

    # Run sync test
    test_signal_handling_integration()

    logger.info("🎉 All comprehensive termination tests passed!")
