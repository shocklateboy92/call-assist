"""Pytest configuration for Call Assist integration tests."""

import asyncio
import logging
import os
import subprocess
import socket
import threading
import time
from typing import Generator, Optional
from unittest.mock import patch

import pytest
import grpc.aio
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Import broker utilities from tests directory
from tests.broker_test_utils import BrokerManager, BrokerClient

from custom_components.call_assist.const import DOMAIN

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry for testing."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "localhost",
            "port": 50051,
        },
        title="Test Call Assist",
        entry_id="test_entry_id",
    )


@pytest.fixture(scope="session")
def broker_manager():
    """Session-scoped broker manager for integration tests."""
    broker_mgr = None
    try:
        broker_mgr = BrokerManager(port=50051)
        if not broker_mgr.start(timeout=15.0):
            logger.warning("Could not start broker - tests may use external broker")
            yield None
        else:
            logger.info("✅ Broker started for integration tests")
            yield broker_mgr
    except Exception as ex:
        logger.warning(f"Broker startup failed: {ex}")
        yield None
    finally:
        if broker_mgr:
            broker_mgr.stop()
            logger.info("🧹 Broker cleaned up")


@pytest.fixture
async def broker_client(broker_manager):
    """Provide gRPC client connection to broker for each test."""
    if broker_manager is None:
        # Try to connect to external broker
        client = BrokerClient(host='localhost', port=50051)
        if not await client.connect():
            pytest.skip("No broker available for testing")
    else:
        client = BrokerClient(host='localhost', port=50051)
        if not await client.connect():
            pytest.fail("Could not connect to started broker")
    
    yield client
    await client.disconnect()


@pytest.fixture
async def integration_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    broker_manager,
) -> Generator[ConfigEntry, None, None]:
    """Set up the Call Assist integration with real broker."""
    # Ensure broker is available
    if broker_manager is None:
        # Check if external broker is available
        client = BrokerClient(host='localhost', port=50051)
        if not await client.connect():
            pytest.skip("No broker available - cannot test integration")
        await client.disconnect()
    
    # Add config entry to hass
    mock_config_entry.add_to_hass(hass)
    
    # Set up the integration
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    
    # Ensure integration is loaded
    await hass.async_block_till_done()
    
    yield mock_config_entry
    
    # Cleanup
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def mock_home_assistant_entities(hass: HomeAssistant):
    """Mock typical Home Assistant entities for testing."""
    # Mock camera entities
    hass.states.async_set("camera.living_room", "idle", {
        "friendly_name": "Living Room Camera",
        "supported_features": 1,  # SUPPORT_STREAM
    })
    hass.states.async_set("camera.kitchen", "idle", {
        "friendly_name": "Kitchen Camera", 
        "supported_features": 1,
    })
    
    # Mock media player entities
    hass.states.async_set("media_player.living_room_tv", "off", {
        "friendly_name": "Living Room TV",
        "supported_features": 152,  # Basic cast support
        "device_class": "tv",
    })
    hass.states.async_set("media_player.kitchen_speaker", "off", {
        "friendly_name": "Kitchen Speaker",
        "supported_features": 152,
        "device_class": "speaker",
    })
    
    return {
        "cameras": ["camera.living_room", "camera.kitchen"],
        "media_players": ["media_player.living_room_tv", "media_player.kitchen_speaker"],
    }


@pytest.fixture
def sample_call_stations():
    """Sample call station data for testing."""
    return [
        {
            "station_id": "living_room",
            "display_name": "Living Room",
            "camera_entity": "camera.living_room",
            "media_player_entity": "media_player.living_room_tv",
            "state": "idle",
        },
        {
            "station_id": "kitchen", 
            "display_name": "Kitchen",
            "camera_entity": "camera.kitchen",
            "media_player_entity": "media_player.kitchen_speaker",
            "state": "idle",
        },
    ]


@pytest.fixture
def sample_contacts():
    """Sample contact data for testing."""
    return [
        {
            "contact_id": "alice",
            "display_name": "Alice Smith",
            "protocol": "matrix",
            "address": "@alice:matrix.org",
            "avatar_url": None,
            "presence": "online",
        },
        {
            "contact_id": "bob",
            "display_name": "Bob Johnson", 
            "protocol": "xmpp",
            "address": "bob@example.com",
            "avatar_url": None,
            "presence": "offline",
        },
    ]


@pytest.fixture
def connection_failure_config():
    """Config entry that will fail to connect to broker."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "nonexistent-broker",
            "port": 99999,
        },
        title="Failed Connection Test",
        entry_id="failed_test_entry",
    )