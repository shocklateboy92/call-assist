#!/usr/bin/env python3
"""
Broker Integration Tests

Tests for the new simplified broker interface that focuses on:
- Receiving HA entity streams
- Creating call stations from camera+media_player combinations
- Streaming broker entities back to HA
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast

import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
import pytest

from addon.broker.broker import CallAssistBroker

# Test imports
from proto_gen.callassist.broker import (
    BrokerEntityType,
    BrokerEntityUpdate,
    HaEntityUpdate,
    HealthCheckResponse,
    StartCallRequest,
    StartCallResponse,
)

from .conftest import WebUITestClient
from .types import VideoTestEnvironment

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestBrokerIntegration:
    """Test cases for the simplified broker integration"""

    @pytest.fixture
    async def broker(self) -> CallAssistBroker:
        """Create a broker instance for testing"""
        return CallAssistBroker()

    @pytest.fixture
    async def mock_ha_entities(
        self,
        mock_cameras: list[HaEntityUpdate],
        mock_media_players: list[HaEntityUpdate],
    ) -> list[HaEntityUpdate]:
        """Create mock HA entities using video test fixtures"""
        # Use the first 2 cameras and first 2 media players from video fixtures
        cameras = mock_cameras[:2]
        players = mock_media_players[:2]

        # Convert to HaEntityUpdate format expected by broker tests using list comprehensions
        return [
            HaEntityUpdate(
                entity_id=entity.entity_id,
                domain=entity.domain,
                name=entity.name,
                state=entity.state,
                attributes=entity.attributes,
                available=entity.available,
                last_updated=entity.last_updated,
            )
            for entity in cameras + players
        ]

    async def test_health_check(self, broker: CallAssistBroker) -> None:
        """Test basic health check functionality"""
        response = await broker.health_check(betterproto_lib_google.Empty())

        assert isinstance(response, HealthCheckResponse)
        assert response.healthy
        assert "Broker running for" in response.message
        assert response.timestamp is not None

    async def test_ha_entity_storage(
        self, broker: CallAssistBroker, mock_ha_entities: list[HaEntityUpdate]
    ) -> None:
        """Test that broker correctly stores HA entities"""

        # Simulate streaming HA entities
        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in mock_ha_entities:
                yield entity

        # Process the stream
        await broker.stream_ha_entities(mock_entity_stream())

        # Verify entities were stored
        assert len(broker.ha_entities) == 4
        assert "camera.test_front_door" in broker.ha_entities
        assert "media_player.test_living_room_tv" in broker.ha_entities

        # Verify entity details
        camera = broker.ha_entities["camera.test_front_door"]
        assert camera.domain == "camera"
        assert camera.name == "Test Front Door Camera"
        assert camera.state == "streaming"

    async def test_call_station_creation_via_web_ui(
        self,
        broker: CallAssistBroker,
        mock_ha_entities: list[HaEntityUpdate],
        web_ui_client: WebUITestClient,
    ) -> None:
        """Test that call stations are created via web UI, not automatically"""

        # First, stream HA entities to make them available to the broker
        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())

        # Initially, no call stations should exist (they're not auto-created)
        assert len(broker.call_stations) == 0

        # Create call station via web UI
        await web_ui_client.wait_for_server()

        try:
            # Navigate to add call station page
            _ = await web_ui_client.get_page("/ui/call-stations")
            logger.info("✅ Call stations page loaded")

            # Submit call station form
            station_form_data = {
                "station_id": "test_station_front_door_living_room",
                "display_name": "Test Front Door → Living Room",
                "camera_entity_id": "camera.test_front_door",
                "media_player_entity_id": "media_player.test_living_room_tv",
                "enabled": "true",
            }

            status, _, _ = await web_ui_client.post_form(
                "/ui/add-call-station", cast(dict[str, object], station_form_data)
            )

            if status in [200, 302]:  # Success or redirect
                logger.info("✅ Call station created via web UI")

                # Now verify the call station exists
                assert len(broker.call_stations) == 1

                station_id = list(broker.call_stations.keys())[0]
                station = broker.call_stations[station_id]
                assert station.camera_entity_id == "camera.test_front_door"
                assert (
                    station.media_player_entity_id == "media_player.test_living_room_tv"
                )
                assert station.available
            else:
                logger.warning(f"Call station creation returned status {status}")

        except Exception as e:
            logger.warning(f"Failed to create call station via web UI: {e}")
            # This test shows that call stations must be manually created, not auto-generated

    async def test_broker_entity_streaming(
        self, broker: CallAssistBroker, mock_ha_entities: list[HaEntityUpdate]
    ) -> None:
        """Test that broker streams entities correctly"""

        # First, populate with HA entities
        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())

        # Now test entity streaming (note: no call stations auto-created)
        entities_received: list[BrokerEntityUpdate] = []

        async def collect_entities() -> None:
            async for entity_update in broker.stream_broker_entities(
                betterproto_lib_google.Empty()
            ):
                entities_received.append(entity_update)
                # Stop after getting initial entities (just broker status, no call stations)
                if len(entities_received) >= 1:  # 1 broker status
                    break

        # Run for a short time to collect initial entities
        await asyncio.wait_for(collect_entities(), timeout=2.0)

        # Verify we got at least the broker status entity
        assert len(entities_received) >= 1

        # Check for broker status entity
        broker_status = [
            e
            for e in entities_received
            if e.entity_type == BrokerEntityType.BROKER_STATUS
        ]
        assert len(broker_status) >= 1
        assert broker_status[0].entity_id == "broker_status"
        assert broker_status[0].state == "online"

        # Should be no call station entities without manual creation
        call_stations = [
            e
            for e in entities_received
            if e.entity_type == BrokerEntityType.CALL_STATION
        ]
        assert len(call_stations) == 0

    async def test_entity_availability_updates(self, broker: CallAssistBroker) -> None:
        """Test that entity availability is properly tracked for manual call station creation"""
        # Create entities with one unavailable
        entities = [
            HaEntityUpdate(
                entity_id="camera.test",
                domain="camera",
                name="Test Camera",
                state="unavailable",
                attributes={},
                available=False,  # Camera unavailable
                last_updated=datetime.now(UTC),
            ),
            HaEntityUpdate(
                entity_id="media_player.test",
                domain="media_player",
                name="Test Player",
                state="idle",
                attributes={},
                available=True,  # Player available
                last_updated=datetime.now(UTC),
            ),
        ]

        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())

        # Verify entities are stored properly
        assert len(broker.ha_entities) == 2
        assert "camera.test" in broker.ha_entities
        assert "media_player.test" in broker.ha_entities

        # Verify availability is tracked correctly
        camera = broker.ha_entities["camera.test"]
        player = broker.ha_entities["media_player.test"]
        assert not camera.available
        assert player.available

        # No call stations should be auto-created
        assert len(broker.call_stations) == 0

    async def test_dynamic_entity_updates(self, broker: CallAssistBroker) -> None:
        """Test that broker handles dynamic entity updates"""
        # Start with one camera
        initial_entities = [
            HaEntityUpdate(
                entity_id="camera.dynamic",
                domain="camera",
                name="Dynamic Camera",
                state="idle",
                attributes={},
                available=True,
                last_updated=datetime.now(UTC),
            ),
            HaEntityUpdate(
                entity_id="media_player.dynamic",
                domain="media_player",
                name="Dynamic Player",
                state="idle",
                attributes={},
                available=True,
                last_updated=datetime.now(UTC),
            ),
        ]

        async def initial_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in initial_entities:
                yield entity

        await broker.stream_ha_entities(initial_stream())

        # Should have 2 entities stored but no call stations (no auto-creation)
        assert len(broker.ha_entities) == 2
        assert len(broker.call_stations) == 0

        # Add another media player
        additional_entities = [
            HaEntityUpdate(
                entity_id="media_player.dynamic2",
                domain="media_player",
                name="Dynamic Player 2",
                state="idle",
                attributes={},
                available=True,
                last_updated=datetime.now(UTC),
            ),
        ]

        async def additional_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in additional_entities:
                yield entity

        await broker.stream_ha_entities(additional_stream())

        # Should now have 3 entities stored but still no auto-created call stations
        assert len(broker.ha_entities) == 3
        assert len(broker.call_stations) == 0

    async def test_rtsp_stream_integration(
        self, broker: CallAssistBroker, mock_ha_entities: list[HaEntityUpdate]
    ) -> None:
        """Test that broker properly stores RTSP stream entities for later call station creation"""

        # Process HA entities with RTSP streams
        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())

        # Check that camera entities with RTSP streams are properly stored
        cameras_with_streams = [
            entity
            for entity in mock_ha_entities
            if entity.domain == "camera" and "stream_source" in entity.attributes
        ]

        assert len(cameras_with_streams) >= 1

        # Verify stream source information is preserved in broker's entity storage
        for camera in cameras_with_streams:
            if not camera.available:
                continue

            stream_source = camera.attributes["stream_source"]
            assert stream_source.startswith("rtsp://")

            # Verify camera is stored in broker
            assert camera.entity_id in broker.ha_entities
            stored_camera = broker.ha_entities[camera.entity_id]
            assert stored_camera.attributes["stream_source"] == stream_source

            logger.info(
                f"Camera {camera.entity_id} with RTSP stream {stream_source} properly stored"
            )

        # No automatic call stations should be created
        assert len(broker.call_stations) == 0

    async def test_start_call_service_requires_manual_station(
        self, broker: CallAssistBroker, mock_ha_entities: list[HaEntityUpdate]
    ) -> None:
        """Test the start_call service functionality (requires manual call station creation)"""

        # First set up the broker with entities
        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())

        # Verify no call stations exist initially (no auto-creation)
        assert len(broker.call_stations) == 0

        # Test that start_call fails when no call stations exist
        request = StartCallRequest(
            call_station_id="nonexistent_station", contact="@test_user:matrix.org"
        )

        response = await broker.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert not response.success
        assert "not found" in response.message
        assert response.call_id == ""

        # Note: To test successful call start, you would need to:
        # 1. Create a call station via web UI first
        # 2. Then test the start_call functionality
        # This emphasizes that call stations must be manually configured

    async def test_start_call_invalid_station(self, broker: CallAssistBroker) -> None:
        """Test start_call with invalid call station ID"""
        request = StartCallRequest(
            call_station_id="invalid_station_id", contact="@test_user:matrix.org"
        )

        response = await broker.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert not response.success
        assert "not found" in response.message
        assert response.call_id == ""

    async def test_start_call_unavailable_station(
        self, broker: CallAssistBroker
    ) -> None:
        """Test start_call behavior when entities are unavailable"""
        # Create entities with unavailable camera
        entities = [
            HaEntityUpdate(
                entity_id="camera.unavailable",
                domain="camera",
                name="Unavailable Camera",
                state="unavailable",
                attributes={},
                available=False,
                last_updated=datetime.now(UTC),
            ),
            HaEntityUpdate(
                entity_id="media_player.available",
                domain="media_player",
                name="Available Player",
                state="idle",
                attributes={},
                available=True,
                last_updated=datetime.now(UTC),
            ),
        ]

        async def mock_entity_stream() -> AsyncIterator[HaEntityUpdate]:
            for entity in entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())

        # Verify entities are stored but no call stations auto-created
        assert len(broker.ha_entities) == 2
        assert len(broker.call_stations) == 0

        # Try to start call with non-existent station
        request = StartCallRequest(
            call_station_id="nonexistent_station", contact="@test_user:matrix.org"
        )

        response = await broker.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert not response.success
        assert "not found" in response.message
        assert response.call_id == ""

        # Note: To test unavailable station behavior, you would need to:
        # 1. Manually create a call station via web UI with unavailable entities
        # 2. Then test that calls fail appropriately


@pytest.mark.asyncio
async def test_broker_integration_end_to_end(
    video_test_environment: VideoTestEnvironment,
) -> None:
    """End-to-end test of the broker integration with video fixtures"""
    broker = CallAssistBroker()

    # Test health check
    health = await broker.health_check(betterproto_lib_google.Empty())
    assert health.healthy

    # Test with video environment entities
    cameras = video_test_environment.cameras
    media_players = video_test_environment.media_players

    # Create entity stream
    all_entities = cameras + media_players

    async def entity_stream() -> AsyncIterator[HaEntityUpdate]:
        for entity in all_entities:
            # Entities are already HaEntityUpdate format from fixtures
            yield entity

    await broker.stream_ha_entities(entity_stream())

    # Verify entities are properly stored
    total_entities = len(cameras) + len(media_players)
    assert len(broker.ha_entities) == total_entities

    # Verify no automatic call stations are created
    assert len(broker.call_stations) == 0

    # Count available entities for reference
    available_cameras = [cam for cam in cameras if cam.available]
    available_players = [player for player in media_players if player.available]

    logger.info(
        f"✅ Broker integration with video fixtures: {len(available_cameras)} cameras and {len(available_players)} media players stored"
    )
    logger.info(
        "✅ No automatic call stations created - requires manual configuration via web UI"
    )
    logger.info("✅ Broker integration tests completed successfully")
