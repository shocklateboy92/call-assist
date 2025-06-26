#!/usr/bin/env python3
"""
Broker Integration Tests

Tests for the new simplified broker interface that focuses on:
- Receiving HA entity streams
- Creating call stations from camera+media_player combinations
- Streaming broker entities back to HA
"""

import asyncio
import pytest
import pytest_asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

# Test imports
from proto_gen.callassist.broker import (
    BrokerIntegrationStub,
    HaEntityUpdate,
    BrokerEntityUpdate,
    BrokerEntityType,
    HealthCheckResponse,
    StartCallRequest,
    StartCallResponse,
)
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
from grpclib.client import Channel

from addon.broker.main import CallAssistBroker

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestBrokerIntegration:
    """Test cases for the simplified broker integration"""

    @pytest.fixture
    async def broker(self):
        """Create a broker instance for testing"""
        return CallAssistBroker()

    @pytest.fixture
    async def mock_ha_entities(self, mock_cameras, mock_media_players):
        """Create mock HA entities using video test fixtures"""
        # Use the first 2 cameras and first 2 media players from video fixtures
        cameras = mock_cameras[:2]
        players = mock_media_players[:2]
        
        # Convert to HaEntityUpdate format expected by broker tests
        entities = []
        
        for camera in cameras:
            entities.append(HaEntityUpdate(
                entity_id=camera.entity_id,
                domain=camera.domain,
                name=camera.name,
                state=camera.state,
                attributes=camera.attributes,
                available=camera.available,
                last_updated=camera.last_updated,
            ))
        
        for player in players:
            entities.append(HaEntityUpdate(
                entity_id=player.entity_id,
                domain=player.domain,
                name=player.name,
                state=player.state,
                attributes=player.attributes,
                available=player.available,
                last_updated=player.last_updated,
            ))
        
        return entities

    async def test_health_check(self, broker):
        """Test basic health check functionality"""
        response = await broker.health_check(betterproto_lib_google.Empty())
        
        assert isinstance(response, HealthCheckResponse)
        assert response.healthy == True
        assert "Broker running for" in response.message
        assert response.timestamp is not None

    async def test_ha_entity_storage(self, broker, mock_ha_entities):
        """Test that broker correctly stores HA entities"""
        # Simulate streaming HA entities
        async def mock_entity_stream():
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

    async def test_call_station_creation(self, broker, mock_ha_entities):
        """Test that call stations are created from camera+media_player combinations"""
        # Process HA entities
        async def mock_entity_stream():
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())
        
        # Should create 4 call stations (2 cameras × 2 media players)
        assert len(broker.call_stations) == 4
        
        # Check specific station
        expected_station_id = "station_camera_test_front_door_media_player_test_living_room_tv"
        assert expected_station_id in broker.call_stations
        
        station = broker.call_stations[expected_station_id]
        assert station.camera_entity_id == "camera.test_front_door"
        assert station.media_player_entity_id == "media_player.test_living_room_tv"
        assert station.name == "Test Front Door Camera + Test Living Room TV"
        assert station.available == True

    async def test_broker_entity_streaming(self, broker, mock_ha_entities):
        """Test that broker streams entities correctly"""
        # First, populate with HA entities
        async def mock_entity_stream():
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())
        
        # Now test entity streaming
        entities_received = []
        
        async def collect_entities():
            async for entity_update in broker.stream_broker_entities(betterproto_lib_google.Empty()):
                entities_received.append(entity_update)
                # Stop after getting initial entities (call stations + broker status)
                if len(entities_received) >= 5:  # 4 call stations + 1 broker status
                    break

        # Run for a short time to collect initial entities
        await asyncio.wait_for(collect_entities(), timeout=2.0)
        
        # Verify we got the expected entities
        assert len(entities_received) == 5
        
        # Check call station entities
        call_stations = [e for e in entities_received if e.entity_type == BrokerEntityType.CALL_STATION]
        assert len(call_stations) == 4
        
        # Check broker status entity
        broker_status = [e for e in entities_received if e.entity_type == BrokerEntityType.BROKER_STATUS]
        assert len(broker_status) == 1
        assert broker_status[0].entity_id == "broker_status"
        assert broker_status[0].state == "online"

    async def test_entity_availability_updates(self, broker):
        """Test that entity availability affects call station availability"""
        # Create entities with one unavailable
        entities = [
            HaEntityUpdate(
                entity_id="camera.test",
                domain="camera",
                name="Test Camera", 
                state="unavailable",
                attributes={},
                available=False,  # Camera unavailable
                last_updated=datetime.now(timezone.utc),
            ),
            HaEntityUpdate(
                entity_id="media_player.test",
                domain="media_player",
                name="Test Player",
                state="idle",
                attributes={},
                available=True,  # Player available
                last_updated=datetime.now(timezone.utc),
            ),
        ]

        async def mock_entity_stream():
            for entity in entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())
        
        # Check that call station is unavailable due to camera being unavailable
        station_id = "station_camera_test_media_player_test"
        assert station_id in broker.call_stations
        
        station = broker.call_stations[station_id]
        assert station.available == False  # Should be false because camera is unavailable

    async def test_dynamic_entity_updates(self, broker):
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
                last_updated=datetime.now(timezone.utc),
            ),
            HaEntityUpdate(
                entity_id="media_player.dynamic",
                domain="media_player",
                name="Dynamic Player",
                state="idle", 
                attributes={},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
        ]

        async def initial_stream():
            for entity in initial_entities:
                yield entity

        await broker.stream_ha_entities(initial_stream())
        
        # Should have 1 call station
        assert len(broker.call_stations) == 1
        
        # Add another media player
        additional_entities = [
            HaEntityUpdate(
                entity_id="media_player.dynamic2",
                domain="media_player",
                name="Dynamic Player 2",
                state="idle",
                attributes={},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
        ]

        async def additional_stream():
            for entity in additional_entities:
                yield entity

        await broker.stream_ha_entities(additional_stream())
        
        # Should now have 2 call stations (1 camera × 2 media players)
        assert len(broker.call_stations) == 2


    async def test_rtsp_stream_integration(self, broker, mock_ha_entities):
        """Test that broker works with RTSP stream entities"""
        # Process HA entities with RTSP streams
        async def mock_entity_stream():
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())
        
        # Check that call stations include stream source information
        cameras_with_streams = [
            entity for entity in mock_ha_entities 
            if entity.domain == "camera" and "stream_source" in entity.attributes
        ]
        
        assert len(cameras_with_streams) >= 1
        
        # Verify stream source is preserved in call stations
        for camera in cameras_with_streams:
            if not camera.available:
                continue
                
            stream_source = camera.attributes["stream_source"]
            assert stream_source.startswith("rtsp://")
            
            # Find call stations using this camera
            matching_stations = [
                station for station in broker.call_stations.values()
                if station.camera_entity_id == camera.entity_id
            ]
            
            assert len(matching_stations) >= 1
            logger.info(f"Camera {camera.entity_id} with stream {stream_source} has {len(matching_stations)} call stations")

    async def test_start_call_service(self, broker, mock_ha_entities):
        """Test the start_call service functionality"""
        # First set up the broker with entities
        async def mock_entity_stream():
            for entity in mock_ha_entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())
        
        # Verify we have call stations
        assert len(broker.call_stations) > 0
        
        # Get a call station ID
        station_id = list(broker.call_stations.keys())[0]
        
        # Test successful call start
        request = StartCallRequest(
            call_station_id=station_id,
            contact="@test_user:matrix.org"
        )
        
        response = await broker.start_call(request)
        
        assert isinstance(response, StartCallResponse)
        assert response.success == True
        assert "Call started successfully" in response.message
        assert response.call_id != ""
        assert response.call_id.startswith("call_")
        
        # Verify call station state changed
        station = broker.call_stations[station_id]
        assert station.state == "calling"
        
    async def test_start_call_invalid_station(self, broker):
        """Test start_call with invalid call station ID"""
        request = StartCallRequest(
            call_station_id="invalid_station_id",
            contact="@test_user:matrix.org"
        )
        
        response = await broker.start_call(request)
        
        assert isinstance(response, StartCallResponse)
        assert response.success == False
        assert "not found" in response.message
        assert response.call_id == ""
        
    async def test_start_call_unavailable_station(self, broker):
        """Test start_call with unavailable call station"""
        # Create entities with unavailable camera
        entities = [
            HaEntityUpdate(
                entity_id="camera.unavailable",
                domain="camera",
                name="Unavailable Camera",
                state="unavailable",
                attributes={},
                available=False,
                last_updated=datetime.now(timezone.utc),
            ),
            HaEntityUpdate(
                entity_id="media_player.available",
                domain="media_player",
                name="Available Player",
                state="idle",
                attributes={},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
        ]

        async def mock_entity_stream():
            for entity in entities:
                yield entity

        await broker.stream_ha_entities(mock_entity_stream())
        
        # Get the station ID (should be unavailable)
        station_id = list(broker.call_stations.keys())[0]
        station = broker.call_stations[station_id]
        assert station.available == False
        
        # Try to start call
        request = StartCallRequest(
            call_station_id=station_id,
            contact="@test_user:matrix.org"
        )
        
        response = await broker.start_call(request)
        
        assert isinstance(response, StartCallResponse)
        assert response.success == False
        assert "not available" in response.message
        assert response.call_id == ""


@pytest.mark.asyncio
async def test_broker_integration_end_to_end(video_test_environment):
    """End-to-end test of the broker integration with video fixtures"""
    broker = CallAssistBroker()
    
    # Test health check
    health = await broker.health_check(betterproto_lib_google.Empty())
    assert health.healthy
    
    # Test with video environment entities
    cameras = video_test_environment["cameras"]
    media_players = video_test_environment["media_players"]
    
    # Create entity stream
    all_entities = cameras + media_players
    
    async def entity_stream():
        for entity in all_entities:
            # Convert to HaEntityUpdate format
            yield HaEntityUpdate(
                entity_id=entity.entity_id,
                domain=entity.domain,
                name=entity.name,
                state=entity.state,
                attributes=entity.attributes,
                available=entity.available,
                last_updated=entity.last_updated,
            )
    
    await broker.stream_ha_entities(entity_stream())
    
    # Verify integration worked
    available_cameras = [cam for cam in cameras if cam.available]
    available_players = [player for player in media_players if player.available]
    expected_stations = len(available_cameras) * len(available_players)
    
    assert len(broker.call_stations) == expected_stations
    
    logger.info(f"✅ Broker integration with video fixtures: {len(broker.call_stations)} call stations created")
    logger.info("✅ Broker integration tests completed successfully")