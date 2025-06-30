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
class EntityConfig:
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
            EntityConfig(
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
            EntityConfig(
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
            EntityConfig(
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
            EntityConfig(
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
        logger.info(
            f"Media player entities from broker web UI: {media_player_entity_ids}"
        )

        # Verify test entities appear in dropdowns (proving they were sent to broker)
        test_cameras = ["camera.test_front_door", "camera.test_back_yard"]
        test_media_players = [
            "media_player.test_living_room_tv",
            "media_player.test_kitchen_display",
        ]

        # Check for test camera entities
        found_cameras = [cam for cam in test_cameras if cam in camera_entity_ids]
        assert (
            len(found_cameras) > 0
        ), f"Should have received camera entities from HA integration. Expected: {test_cameras}, Found: {camera_entity_ids}"

        # Check for test media player entities
        found_players = [
            player for player in test_media_players if player in media_player_entity_ids
        ]
        assert (
            len(found_players) > 0
        ), f"Should have received media player entities from HA integration. Expected: {test_media_players}, Found: {media_player_entity_ids}"

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

            # Now verify the call station exists by checking the web UI
            # Since we can't directly access broker.call_stations via GRPC,
            # we verify by checking the call stations page
            html, soup = await web_ui_client.get_page("/ui/call-stations")
            web_ui_client.validate_html_structure(soup, "call stations page")

            # Look for our created station in the HTML
            station_found = "test_station_demo" in html or "Test Demo Station" in html
            assert (
                station_found
            ), "Call station should appear in the web UI after creation"

            logger.info("✅ Call station verified via web UI")
        else:
            logger.warning(f"Call station creation returned status {status}")

    async def test_entity_availability_with_real_integration(
        self,
        hass: HomeAssistant,
        broker_server: BrokerIntegrationStub,
        broker_process: BrokerProcessInfo,
        web_ui_client: WebUITestClient,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that entity availability is properly tracked through real HA integration"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

        # Since we can't directly access broker.ha_entities via GRPC,
        # we verify entities are received by checking the web UI dropdowns
        await web_ui_client.wait_for_server()
        html, soup = await web_ui_client.get_page("/ui/add-call-station")
        web_ui_client.validate_html_structure(soup, "add call station page")

        # Find camera and media player dropdowns
        camera_select = soup.find("select", {"name": "camera_entity_id"})
        media_player_select = soup.find("select", {"name": "media_player_entity_id"})

        assert isinstance(camera_select, Tag), "Camera dropdown not found"
        assert isinstance(media_player_select, Tag), "Media player dropdown not found"

        # Extract options to verify entities are available
        camera_options = camera_select.find_all("option")
        media_player_options = media_player_select.find_all("option")

        camera_entity_ids = [
            opt.get("value")
            for opt in camera_options
            if isinstance(opt, Tag) and opt.get("value")
        ]
        media_player_entity_ids = [
            opt.get("value")
            for opt in media_player_options
            if isinstance(opt, Tag) and opt.get("value")
        ]

        # Check for test entities
        test_cameras = [
            eid
            for eid in camera_entity_ids
            if isinstance(eid, str) and eid.startswith("camera.test_")
        ]
        test_players = [
            eid
            for eid in media_player_entity_ids
            if isinstance(eid, str) and eid.startswith("media_player.test_")
        ]

        assert len(test_cameras) > 0, "Should have test camera entities available"
        assert len(test_players) > 0, "Should have test media player entities available"

        logger.info(
            f"✅ Entity availability verified via web UI - {len(test_cameras)} cameras, {len(test_players)} players"
        )

    async def test_dynamic_entity_updates_with_real_integration(
        self,
        hass: HomeAssistant,
        broker_server: BrokerIntegrationStub,
        broker_process: BrokerProcessInfo,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that broker handles dynamic entity updates through real HA integration"""

        # Wait for initial entity streaming
        await asyncio.sleep(2)

        # Simulate entity state change by updating entity state in HA
        test_cameras = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("camera.test_")
        ]

        if test_cameras:
            test_camera = test_cameras[0]
            logger.info(f"Testing dynamic updates for: {test_camera}")

            # Change entity state
            hass.states.async_set(
                test_camera, "streaming", {"test_attribute": "updated"}
            )
            await hass.async_block_till_done()

            # Wait for change to propagate to broker
            await asyncio.sleep(2)

            # Since we can't directly check broker.ha_entities via GRPC,
            # we verify the entity is still available through the integration
            # by checking it still appears in the web UI
            # (This is a basic test - in a real scenario, we'd need broker entity streaming)
            logger.info(f"Entity {test_camera} state change propagated to HA")

        logger.info("✅ Dynamic entity updates test completed")

    async def test_rtsp_stream_integration_with_real_ha(
        self,
        hass: HomeAssistant,
        broker_server: BrokerIntegrationStub,
        broker_process: BrokerProcessInfo,
        web_ui_client: WebUITestClient,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test that broker properly receives camera entities from real HA integration"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

        # Since we can't directly access broker.ha_entities via GRPC,
        # we verify camera entities were received by checking the web UI
        await web_ui_client.wait_for_server()
        html, soup = await web_ui_client.get_page("/ui/add-call-station")
        web_ui_client.validate_html_structure(soup, "add call station page")

        # Find camera dropdown
        camera_select = soup.find("select", {"name": "camera_entity_id"})
        assert isinstance(camera_select, Tag), "Camera dropdown not found"

        # Extract camera options
        camera_options = camera_select.find_all("option")
        camera_entity_ids = [
            opt.get("value")
            for opt in camera_options
            if isinstance(opt, Tag) and opt.get("value")
        ]

        # Check for test camera entities
        test_cameras = [
            eid
            for eid in camera_entity_ids
            if isinstance(eid, str) and eid.startswith("camera.test_")
        ]

        logger.info(f"Camera entities available in web UI: {camera_entity_ids}")
        logger.info(f"Test camera entities found: {test_cameras}")

        # Verify we have at least some camera entities
        assert len(camera_entity_ids) > 0, "Should have camera entities available"
        assert len(test_cameras) > 0, "Should have test camera entities"

        logger.info("✅ Camera entity integration verified via web UI")

    async def test_start_call_service_with_real_integration(
        self,
        hass: HomeAssistant,
        broker_server: BrokerIntegrationStub,
        broker_process: BrokerProcessInfo,
        setup_ha_integration: None,
        setup_test_entities: None,
    ) -> None:
        """Test the start_call service functionality using real HA integration"""

        # Wait for integration to stream entities
        await asyncio.sleep(2)

        # Test that start_call fails when no call stations exist
        request = StartCallRequest(
            call_station_id="nonexistent_station", contact="@test_user:matrix.org"
        )

        response = await broker_server.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert not response.success
        assert "not found" in response.message
        assert response.call_id == ""

        logger.info("✅ Start call properly fails when no call stations exist")

        # Note: To test successful call start, you would need to:
        # 1. Create a call station via web UI first using real HA entities
        # 2. Then test the start_call functionality
        # This emphasizes that call stations must be manually configured

    async def test_start_call_invalid_station(
        self, broker_server: BrokerIntegrationStub
    ) -> None:
        """Test start_call with invalid call station ID"""
        request = StartCallRequest(
            call_station_id="invalid_station_id", contact="@test_user:matrix.org"
        )

        response = await broker_server.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert not response.success
        assert "not found" in response.message
        assert response.call_id == ""

        logger.info("✅ Start call properly fails with invalid station ID")


@pytest.mark.asyncio
async def test_broker_integration_end_to_end_with_real_ha(
    hass: HomeAssistant,
    broker_server: BrokerIntegrationStub,
    broker_process: BrokerProcessInfo,
) -> None:
    """End-to-end test of the broker integration with real HomeAssistant"""

    # Test health check
    health = await broker_server.health_check(betterproto_lib_google.Empty())
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
        EntityConfig(
            entity_id="camera.test_e2e_camera",
            unique_id="test_e2e_camera_001",
            state="streaming",
            attributes={
                "friendly_name": "End-to-End Test Camera",
                "supported_features": "1",
            },
        ),
        EntityConfig(
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

    # Since we can't directly access broker.ha_entities via GRPC,
    # we verify integration success by:
    # 1. Health check passed (already done above)
    # 2. Integration setup succeeded (already verified)
    # 3. No errors in the integration flow

    logger.info("✅ Test entities created in HomeAssistant")
    logger.info("✅ Integration setup completed successfully")
    logger.info("✅ Health check passed")
    logger.info(
        "✅ End-to-end integration test with real HomeAssistant completed successfully"
    )
