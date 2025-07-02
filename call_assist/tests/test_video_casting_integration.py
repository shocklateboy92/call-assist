#!/usr/bin/env python3

import asyncio
import pytest
from datetime import UTC, datetime

from addon.broker.casting_service import CastingService, CastTarget, CastTargetType
from addon.broker.providers.chromecast_provider import ChromecastProvider
from addon.broker.video_streaming_service import VideoFrame, VideoStreamingService


@pytest.mark.asyncio
async def test_video_streaming_service_initialization():
    """Test that video streaming service initializes correctly"""
    service = VideoStreamingService()

    # Check initial state
    assert len(service.get_active_streams()) == 0
    assert service.get_recent_frames("test_call") == []

    # Start cleanup task
    await service.start_cleanup_task()

    # Get stats
    stats = service.get_stream_stats()
    assert stats.active_streams == 0
    assert stats.total_stored_frames == 0
    assert stats.frame_subscribers == 0


@pytest.mark.asyncio
async def test_casting_service_initialization():
    """Test that casting service initializes correctly"""
    video_service = VideoStreamingService()
    casting_service = CastingService(video_service)

    # Register Chromecast provider
    chromecast_provider = ChromecastProvider()
    casting_service.register_provider(chromecast_provider)

    # Check provider registration
    assert CastTargetType.CHROMECAST in casting_service.providers
    assert casting_service.providers[CastTargetType.CHROMECAST] == chromecast_provider

    # Initialize (this will fail if pychromecast is not available, but that's expected)
    await casting_service.initialize()

    # Check initial state
    sessions = await casting_service.get_active_sessions()
    assert len(sessions) == 0

    # Cleanup
    await casting_service.cleanup()


@pytest.mark.asyncio
async def test_video_frame_subscription():
    """Test video frame subscription mechanism"""
    service = VideoStreamingService()

    # Subscribe to frames
    frame_queue = service.subscribe_to_frames()
    assert len(service.frame_subscribers) == 1

    # Create a test frame
    test_frame = VideoFrame(
        call_id="test_call_123",
        stream_id="test_stream_456",
        timestamp=datetime.now(UTC),
        width=640,
        height=480,
        format="i420",
        frame_data=b"fake_frame_data",
        rotation=0,
    )

    # Send frame through the service (simulate)
    await service._store_frame(test_frame)
    await service._notify_frame_subscribers(test_frame)

    # Check that frame was received
    assert not frame_queue.empty()
    received_frame = frame_queue.get_nowait()
    assert received_frame.call_id == "test_call_123"
    assert received_frame.width == 640
    assert received_frame.height == 480

    # Check stored frames
    recent_frames = service.get_recent_frames("test_call_123", count=5)
    assert len(recent_frames) == 1
    assert recent_frames[0].call_id == "test_call_123"

    # Unsubscribe
    service.unsubscribe_from_frames(frame_queue)
    assert len(service.frame_subscribers) == 0


@pytest.mark.asyncio
async def test_provider_interface():
    """Test the provider interface"""
    provider = ChromecastProvider()

    # Test basic properties
    assert provider.target_type == CastTargetType.CHROMECAST
    assert provider.provider_name == "Chromecast Provider"

    # Test initialization (may fail if pychromecast not available)
    initialized = await provider.initialize()
    # Don't assert success since pychromecast may not be installed

    # Test discovery (should return empty list if no pychromecast)
    targets = await provider.discover_targets()
    assert isinstance(targets, list)

    # Cleanup
    await provider.cleanup()


def test_cast_target_creation():
    """Test CastTarget dataclass"""
    target = CastTarget(
        target_id="chromecast_test_123",
        name="Test Chromecast",
        target_type=CastTargetType.CHROMECAST,
        connection_info={
            "host": "192.168.1.100",
            "port": "8009",
            "uuid": "test-uuid-123",
        },
        enabled=True,
    )

    assert target.target_id == "chromecast_test_123"
    assert target.name == "Test Chromecast"
    assert target.target_type == CastTargetType.CHROMECAST
    assert target.enabled is True
    assert target.connection_info["host"] == "192.168.1.100"


if __name__ == "__main__":
    # Run a simple test
    asyncio.run(test_video_streaming_service_initialization())
    print("✅ Video streaming service test passed")

    asyncio.run(test_casting_service_initialization())
    print("✅ Casting service test passed")

    asyncio.run(test_video_frame_subscription())
    print("✅ Frame subscription test passed")

    asyncio.run(test_provider_interface())
    print("✅ Provider interface test passed")

    test_cast_target_creation()
    print("✅ Cast target creation test passed")

    print("🎉 All casting integration tests passed!")
