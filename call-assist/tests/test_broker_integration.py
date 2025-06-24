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
    async def mock_ha_entities(self):
        """Create mock HA entities for testing"""
        return [
            HaEntityUpdate(
                entity_id="camera.front_door",
                domain="camera",
                name="Front Door Camera",
                state="idle",
                attributes={"resolution": "1080p", "fps": "30"},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
            HaEntityUpdate(
                entity_id="camera.back_yard",
                domain="camera", 
                name="Back Yard Camera",
                state="streaming",
                attributes={"resolution": "720p", "fps": "15"},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
            HaEntityUpdate(
                entity_id="media_player.living_room",
                domain="media_player",
                name="Living Room Speaker",
                state="idle",
                attributes={"volume_level": "0.5"},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
            HaEntityUpdate(
                entity_id="media_player.kitchen",
                domain="media_player",
                name="Kitchen Display",
                state="playing",
                attributes={"volume_level": "0.3", "media_title": "News"},
                available=True,
                last_updated=datetime.now(timezone.utc),
            ),
        ]

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
        assert "camera.front_door" in broker.ha_entities
        assert "media_player.living_room" in broker.ha_entities
        
        # Verify entity details
        camera = broker.ha_entities["camera.front_door"]
        assert camera.domain == "camera"
        assert camera.name == "Front Door Camera"
        assert camera.state == "idle"

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
        expected_station_id = "station_camera_front_door_media_player_living_room"
        assert expected_station_id in broker.call_stations
        
        station = broker.call_stations[expected_station_id]
        assert station.camera_entity_id == "camera.front_door"
        assert station.media_player_entity_id == "media_player.living_room"
        assert station.name == "Front Door Camera + Living Room Speaker"
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


@pytest.mark.asyncio
async def test_broker_integration_end_to_end():
    """End-to-end test of the broker integration"""
    broker = CallAssistBroker()
    
    # Test health check
    health = await broker.health_check(betterproto_lib_google.Empty())
    assert health.healthy
    
    logger.info("✅ Broker integration tests completed successfully")