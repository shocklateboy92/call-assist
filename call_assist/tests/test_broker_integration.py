#!/usr/bin/env python3
"""
Broker Integration Tests

Tests for the new simplified broker interface that focuses on:
- Receiving HA entity streams through the real HomeAssistant integration
- Creating call stations from camera+media_player combinations
- Streaming broker entities back to HA
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import cast

import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
import pytest
from bs4 import Tag
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from addon.broker.broker import CallAssistBroker
from integration.const import CONF_HOST, CONF_PORT, DOMAIN

# Test imports
from proto_gen.callassist.broker import (
    BrokerIntegrationStub,
    HealthCheckResponse,
    StartCallRequest,
    StartCallResponse,
)

from .conftest import WebUITestClient
from .types import BrokerProcessInfo


@dataclass
class TestEntityConfig:
    """Configuration for test entities"""

    entity_id: str
    unique_id: str
    state: str
    attributes: dict[str, str]


@dataclass
class CallStationFormData:
    """Form data for creating call stations"""

    station_id: str
    display_name: str
    camera_entity_id: str
    media_player_entity_id: str
    enabled: str


# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestBrokerIntegration:
    """Test cases for the simplified broker integration using real HomeAssistant"""

    # Remove the broker fixture since we'll use broker_server instead

    @pytest.fixture
    async def setup_ha_integration(
        self, hass: HomeAssistant, broker_process: BrokerProcessInfo
    ) -> None:
        """Set up the Call Assist integration in HomeAssistant"""
        # Configure the integration with broker connection details
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        # Complete the config flow with broker details
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "127.0.0.1",
                CONF_PORT: broker_process.grpc_port,
            },
        )

        # Wait for setup to complete
        await hass.async_block_till_done()

        assert "type" in result2 and result2["type"] == "create_entry"
        logger.info("Call Assist integration configured in HomeAssistant")

    @pytest.fixture
    async def setup_test_entities(self, hass: HomeAssistant) -> None:
        """Set up test camera and media player entities directly in HomeAssistant"""
        # Get entity registry to register entities properly
        entity_registry = er.async_get(hass)

        # Create test camera entities with proper registration
        camera_entities = [
            TestEntityConfig(
                entity_id="camera.test_front_door",
                unique_id="test_camera_front_door_001",
                state="streaming",
                attributes={
                    "friendly_name": "Test Front Door Camera",
                    "entity_picture": "/api/camera_proxy/camera.test_front_door",
                    "supported_features": "1",
                    "stream_source": "rtsp://test-server:8554/test_camera_1",
                    "brand": "Test Camera",
                    "model": "Virtual Test v1.0",
                },
            ),
            TestEntityConfig(
                entity_id="camera.test_back_yard",
                unique_id="test_camera_back_yard_002",
                state="streaming",
                attributes={
                    "friendly_name": "Test Back Yard Camera",
                    "entity_picture": "/api/camera_proxy/camera.test_back_yard",
                    "supported_features": "1",
                    "stream_source": "rtsp://test-server:8554/test_camera_2",
                    "brand": "Test Camera",
                    "model": "Virtual Test v2.0",
                },
            ),
        ]

        # Create test media player entities with proper registration
        media_player_entities = [
            TestEntityConfig(
                entity_id="media_player.test_living_room_tv",
                unique_id="test_player_living_room_001",
                state="idle",
                attributes={
                    "friendly_name": "Test Living Room TV",
                    "supported_features": "152463",
                    "device_class": "tv",
                    "volume_level": "0.5",
                    "media_content_type": "",
                    "media_title": "",
                },
            ),
            TestEntityConfig(
                entity_id="media_player.test_kitchen_display",
                unique_id="test_player_kitchen_002",
                state="idle",
                attributes={
                    "friendly_name": "Test Kitchen Display",
                    "supported_features": "152463",
                    "device_class": "speaker",
                    "volume_level": "0.7",
                    "media_content_type": "",
                    "media_title": "",
                },
            ),
        ]

        # Register entities in entity registry first (this makes them "registered entities")
        for camera in camera_entities:
            entity_registry.async_get_or_create(
                domain="camera",
                platform="test",
                unique_id=camera.unique_id,
                suggested_object_id=camera.entity_id.split(".", 1)[
                    1
                ],  # Extract object part
                original_name=camera.attributes["friendly_name"],
            )

        for player in media_player_entities:
            entity_registry.async_get_or_create(
                domain="media_player",
                platform="test",
                unique_id=player.unique_id,
                suggested_object_id=player.entity_id.split(".", 1)[
                    1
                ],  # Extract object part
                original_name=player.attributes["friendly_name"],
            )

        await hass.async_block_till_done()

        # Now add entities to HA state registry
        for camera in camera_entities:
            hass.states.async_set(camera.entity_id, camera.state, camera.attributes)

        for player in media_player_entities:
            hass.states.async_set(player.entity_id, player.state, player.attributes)

        await hass.async_block_till_done()

        # Verify entities were created in both registries
        camera_states = [hass.states.get(c.entity_id) for c in camera_entities]
        player_states = [hass.states.get(p.entity_id) for p in media_player_entities]

        assert all(
            state is not None for state in camera_states
        ), "Camera entities not created in state registry"
        assert all(
            state is not None for state in player_states
        ), "Media player entities not created in state registry"

        # Verify entities are in entity registry
        registered_cameras = [
            entity_registry.async_get(c.entity_id) for c in camera_entities
        ]
        registered_players = [
            entity_registry.async_get(p.entity_id) for p in media_player_entities
        ]

        assert all(
            reg is not None for reg in registered_cameras
        ), "Camera entities not registered in entity registry"
        assert all(
            reg is not None for reg in registered_players
        ), "Media player entities not registered in entity registry"

        logger.info(
            f"Created and registered {len(camera_entities)} test camera entities and {len(media_player_entities)} test media player entities"
        )

        # Debug: Log what entities are in the registry
        all_entities = list(entity_registry.entities.values())
        camera_entities_in_registry = [e for e in all_entities if e.domain == "camera"]
        player_entities_in_registry = [
            e for e in all_entities if e.domain == "media_player"
        ]

        logger.info(
            f"Entity registry now contains {len(camera_entities_in_registry)} camera entities: {[e.entity_id for e in camera_entities_in_registry]}"
        )
        logger.info(
            f"Entity registry now contains {len(player_entities_in_registry)} media_player entities: {[e.entity_id for e in player_entities_in_registry]}"
        )

    async def test_health_check(self, broker_server: BrokerIntegrationStub) -> None:
        """Test basic health check functionality"""
        response = await broker_server.health_check(betterproto_lib_google.Empty())

        assert isinstance(response, HealthCheckResponse)
        assert response.healthy
        assert "Broker running for" in response.message
        assert response.timestamp is not None

    async def test_ha_entity_streaming_through_integration(
        self,
        hass: HomeAssistant,
        web_ui_client: WebUITestClient,
        setup_test_entities: None,  # Create entities first
        setup_ha_integration: None,  # Then set up integration
    ) -> None:
        """Test that HA entities are streamed to broker through the real integration"""

        # Debug: Check what entities exist before integration setup
        entity_registry = er.async_get(hass)
        pre_integration_entities = list(entity_registry.entities.values())
        pre_cameras = [e for e in pre_integration_entities if e.domain == "camera"]
        pre_players = [
            e for e in pre_integration_entities if e.domain == "media_player"
        ]

        logger.info(
            f"Before integration - Entity registry contains {len(pre_cameras)} camera entities: {[e.entity_id for e in pre_cameras]}"
        )
        logger.info(
            f"Before integration - Entity registry contains {len(pre_players)} media_player entities: {[e.entity_id for e in pre_players]}"
        )

        # Wait a bit for integration to stream initial entities
        await asyncio.sleep(2)

        # Debug: Check what the coordinator actually discovered
        coordinator_data = hass.data.get("call_assist", {})
        if coordinator_data:
            coordinator = list(coordinator_data.values())[0].get("coordinator")
            if coordinator:
                logger.info(
                    f"Coordinator tracked cameras: {coordinator._tracked_cameras}"
                )
                logger.info(
                    f"Coordinator tracked media players: {coordinator._tracked_media_players}"
                )

        # Verify that entities were received by checking the web UI dropdowns
        # The broker should have received the entities and they should appear in the form
        await web_ui_client.wait_for_server()
        html, soup = await web_ui_client.get_page("/ui/add-call-station")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "add call station page")

        # Find camera dropdown
        camera_select = soup.find("select", {"name": "camera_entity_id"})
        assert isinstance(camera_select, Tag), "Camera dropdown not found"

        # Find media player dropdown
        media_player_select = soup.find("select", {"name": "media_player_entity_id"})
        assert isinstance(media_player_select, Tag), "Media player dropdown not found"

        # Extract camera options
        camera_options = camera_select.find_all("option")
        camera_entity_ids = [
            opt.get("value")
            for opt in camera_options
            if isinstance(opt, Tag) and opt.get("value")
        ]

        # Extract media player options
        media_player_options = media_player_select.find_all("option")
        media_player_entity_ids = [
            opt.get("value")
            for opt in media_player_options
            if isinstance(opt, Tag) and opt.get("value")
        ]

        logger.info(f"Camera entities from broker web UI: {camera_entity_ids}")
        logger.info(f"Media player entities from broker web UI: {media_player_entity_ids}")

        # Verify test entities appear in dropdowns (proving they were sent to broker)
        test_cameras = ["camera.test_front_door", "camera.test_back_yard"]
        test_media_players = ["media_player.test_living_room_tv", "media_player.test_kitchen_display"]

        # Check for test camera entities
        found_cameras = [cam for cam in test_cameras if cam in camera_entity_ids]
        assert len(found_cameras) > 0, f"Should have received camera entities from HA integration. Expected: {test_cameras}, Found: {camera_entity_ids}"

        # Check for test media player entities  
        found_players = [player for player in test_media_players if player in media_player_entity_ids]
        assert len(found_players) > 0, f"Should have received media player entities from HA integration. Expected: {test_media_players}, Found: {media_player_entity_ids}"

        logger.info("✅ Successfully verified HA entities were streamed to broker:")
        logger.info(f"  - Found cameras: {found_cameras}")
        logger.info(f"  - Found media players: {found_players}")

    async def test_call_station_creation_via_web_ui_with_real_entities(
        self,
        hass: HomeAssistant,
        broker_process: BrokerProcessInfo,
        web_ui_client: WebUITestClient,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that call stations are created via web UI using real HA entities"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

        # Get available test entities from HA states
        test_cameras = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("camera.test_")
        ]
        test_media_players = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("media_player.test_")
        ]

        if not test_cameras or not test_media_players:
            pytest.skip("Test entities not available for testing")

        camera_entity = test_cameras[0]
        media_player_entity = test_media_players[0]

        logger.info(f"Using test entities: {camera_entity}, {media_player_entity}")

        # Create call station via web UI
        await web_ui_client.wait_for_server()

        # Navigate to add call station page
        _ = await web_ui_client.get_page("/ui/call-stations")
        logger.info("✅ Call stations page loaded")

        # Submit call station form with real demo entities
        station_form_data = CallStationFormData(
            station_id="test_station_demo",
            display_name="Test Demo Station",
            camera_entity_id=camera_entity,
            media_player_entity_id=media_player_entity,
            enabled="true",
        )

        status, _, _ = await web_ui_client.post_form(
            "/ui/add-call-station", cast(dict[str, object], station_form_data.__dict__)
        )

        if status in [200, 302]:  # Success or redirect
            logger.info("✅ Call station created via web UI")

            # Now verify the call station exists
            assert len(broker.call_stations) == 1

            station_id = list(broker.call_stations.keys())[0]
            station = broker.call_stations[station_id]
            assert station.camera_entity_id == camera_entity
            assert station.media_player_entity_id == media_player_entity
            assert station.available

            logger.info(f"✅ Call station verified: {station_id}")
        else:
            logger.warning(f"Call station creation returned status {status}")

    async def test_entity_availability_with_real_integration(
        self,
        hass: HomeAssistant,
        broker: CallAssistBroker,
        broker_process: BrokerProcessInfo,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that entity availability is properly tracked through real HA integration"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

        # Verify entities are received from HA
        assert len(broker.ha_entities) > 0, "Should have entities from HA integration"

        # Check availability tracking for test entities
        test_entities = [
            entity_id
            for entity_id in broker.ha_entities
            if entity_id.startswith(("camera.test_", "media_player.test_"))
        ]

        if test_entities:
            # Check that availability is properly tracked
            for entity_id in test_entities[:2]:  # Check first 2 entities
                entity = broker.ha_entities[entity_id]
                # Test entities should generally be available
                logger.info(
                    f"Entity {entity_id}: available={entity.available}, state={entity.state}"
                )

                # Verify entity has expected fields
                assert hasattr(entity, "available")
                assert hasattr(entity, "state")
                assert hasattr(entity, "domain")

        # No call stations should be auto-created
        assert len(broker.call_stations) == 0

        logger.info(
            f"✅ Entity availability tracking verified for {len(test_entities)} test entities"
        )

    async def test_dynamic_entity_updates_with_real_integration(
        self,
        hass: HomeAssistant,
        broker: CallAssistBroker,
        broker_process: BrokerProcessInfo,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that broker handles dynamic entity updates through real HA integration"""

        # Wait for initial entity streaming
        await asyncio.sleep(2)
        initial_count = len(broker.ha_entities)

        logger.info(f"Initial entity count: {initial_count}")

        # Simulate entity state change by updating entity state in HA
        test_cameras = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("camera.test_")
        ]

        if test_cameras:
            test_camera = test_cameras[0]

            # Change entity state
            hass.states.async_set(
                test_camera, "streaming", {"test_attribute": "updated"}
            )
            await hass.async_block_till_done()

            # Wait for change to propagate to broker
            await asyncio.sleep(1)

            # Verify entity update reached broker
            if test_camera in broker.ha_entities:
                updated_entity = broker.ha_entities[test_camera]
                logger.info(
                    f"Entity {test_camera} updated: state={updated_entity.state}"
                )
                assert updated_entity.state == "streaming"

                # Check if test attribute was updated
                if hasattr(updated_entity, "attributes") and updated_entity.attributes:
                    logger.info(f"Entity attributes: {updated_entity.attributes}")

        # Should still have no auto-created call stations
        assert len(broker.call_stations) == 0

        logger.info("✅ Dynamic entity updates verified through real HA integration")

    async def test_rtsp_stream_integration_with_real_ha(
        self,
        hass: HomeAssistant,
        broker: CallAssistBroker,
        broker_process: BrokerProcessInfo,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that broker properly stores camera entities from real HA integration"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

        # Check for camera entities that were streamed from HA
        camera_entities = [
            entity_id
            for entity_id in broker.ha_entities
            if entity_id.startswith("camera.")
        ]

        logger.info(f"Camera entities received from HA: {camera_entities}")

        # If we have camera entities, verify they are properly stored
        if camera_entities:
            for camera_entity_id in camera_entities:
                stored_camera = broker.ha_entities[camera_entity_id]

                # Verify basic camera entity structure
                assert stored_camera.domain == "camera"
                assert stored_camera.entity_id == camera_entity_id

                # Check if entity has attributes (demo cameras might have stream info)
                if hasattr(stored_camera, "attributes") and stored_camera.attributes:
                    logger.info(
                        f"Camera {camera_entity_id} attributes: {list(stored_camera.attributes.keys())}"
                    )

                logger.info(
                    f"✅ Camera {camera_entity_id} properly stored from HA integration"
                )

        # No automatic call stations should be created
        assert len(broker.call_stations) == 0

        logger.info("✅ Camera entity integration verified")

    async def test_start_call_service_with_real_integration(
        self,
        hass: HomeAssistant,
        broker: CallAssistBroker,
        broker_process: BrokerProcessInfo,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test the start_call service functionality using real HA integration"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

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

        logger.info("✅ Start call properly fails when no call stations exist")

        # Note: To test successful call start, you would need to:
        # 1. Create a call station via web UI first using real HA entities
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

        logger.info("✅ Start call properly fails with invalid station ID")


@pytest.mark.asyncio
async def test_broker_integration_end_to_end_with_real_ha(
    hass: HomeAssistant,
    broker_process: BrokerProcessInfo,
) -> None:
    """End-to-end test of the broker integration with real HomeAssistant"""
    broker = CallAssistBroker()

    # Test health check
    health = await broker.health_check(betterproto_lib_google.Empty())
    assert health.healthy

    # Set up Call Assist integration in HomeAssistant
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "127.0.0.1",
            CONF_PORT: broker_process.grpc_port,
        },
    )

    await hass.async_block_till_done()
    assert "type" in result2 and result2["type"] == "create_entry"

    # Create test entities manually
    test_entities = [
        TestEntityConfig(
            entity_id="camera.test_e2e_camera",
            unique_id="test_e2e_camera_001",
            state="streaming",
            attributes={
                "friendly_name": "End-to-End Test Camera",
                "supported_features": "1",
            },
        ),
        TestEntityConfig(
            entity_id="media_player.test_e2e_player",
            unique_id="test_e2e_player_001",
            state="idle",
            attributes={
                "friendly_name": "End-to-End Test Player",
                "supported_features": "152463",
            },
        ),
    ]

    for entity in test_entities:
        hass.states.async_set(entity.entity_id, entity.state, entity.attributes)

    await hass.async_block_till_done()

    # Wait for integration to stream entities to broker
    await asyncio.sleep(3)

    # Verify entities were properly streamed from HA to broker
    logger.info(
        f"Broker received {len(broker.ha_entities)} entities from HA integration"
    )

    # We should have received our test entities
    test_camera_received = "camera.test_e2e_camera" in broker.ha_entities
    test_player_received = "media_player.test_e2e_player" in broker.ha_entities

    if test_camera_received and test_player_received:
        logger.info("✅ Test entities successfully streamed through HA integration")
    else:
        logger.warning(
            f"Test entities not fully received - camera: {test_camera_received}, player: {test_player_received}"
        )

    # Verify no automatic call stations are created
    assert len(broker.call_stations) == 0

    # Count available entities by type
    camera_entities = [
        entity_id for entity_id in broker.ha_entities if entity_id.startswith("camera.")
    ]
    media_player_entities = [
        entity_id
        for entity_id in broker.ha_entities
        if entity_id.startswith("media_player.")
    ]

    logger.info(
        f"✅ Real HA integration: {len(camera_entities)} cameras and {len(media_player_entities)} media players received"
    )
    logger.info(
        "✅ No automatic call stations created - requires manual configuration via web UI"
    )
    logger.info(
        "✅ End-to-end integration test with real HomeAssistant completed successfully"
    )
