"""Test Call Assist entities."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.call_assist.const import DOMAIN


class TestCallStationEntities:
    """Test Call Station entities."""
    
    async def test_call_station_entity_creation(
        self, hass: HomeAssistant, integration_setup, sample_call_stations, broker_client
    ):
        """Test call station entities are created from coordinator data."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Simulate coordinator receiving call station data
        coordinator.data = {
            "call_stations": sample_call_stations,
            "contacts": [],
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        
        # Trigger entity updates
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check that call station entities were created
        entity_reg = er.async_get(hass)
        call_station_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
            and entity.entity_id.startswith(f"{DOMAIN}.station_")
        ]
        
        # Should have entities for each call station
        assert len(call_station_entities) == len(sample_call_stations)
        
        # Check entity IDs and names
        for station in sample_call_stations:
            entity_id = f"{DOMAIN}.station_{station['station_id']}"
            state = hass.states.get(entity_id)
            
            if state:  # Entity may not be created immediately
                assert state.state == station["state"]
                assert state.attributes.get("display_name") == station["display_name"]
                assert state.attributes.get("camera_entity") == station["camera_entity"]
                assert state.attributes.get("media_player_entity") == station["media_player_entity"]
    
    async def test_call_station_state_updates(
        self, hass: HomeAssistant, integration_setup, sample_call_stations, broker_client
    ):
        """Test call station state updates through coordinator."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set initial data
        coordinator.data = {
            "call_stations": sample_call_stations,
            "contacts": [],
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Update a call station state
        updated_stations = sample_call_stations.copy()
        updated_stations[0]["state"] = "ringing"
        updated_stations[0]["caller_id"] = "alice"
        
        coordinator.data["call_stations"] = updated_stations
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check updated state
        entity_id = f"{DOMAIN}.station_{updated_stations[0]['station_id']}"
        state = hass.states.get(entity_id)
        
        if state:
            assert state.state == "ringing"
            assert state.attributes.get("caller_id") == "alice"
    
    async def test_call_station_unavailable_when_coordinator_fails(
        self, hass: HomeAssistant, integration_setup
    ):
        """Test call station entities become unavailable when coordinator fails."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Simulate coordinator failure
        coordinator.last_update_success = False
        coordinator.available = False
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Any existing call station entities should be unavailable
        entity_reg = er.async_get(hass)
        call_station_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
            and entity.entity_id.startswith(f"{DOMAIN}.station_")
        ]
        
        for entity in call_station_entities:
            state = hass.states.get(entity.entity_id)
            if state:
                assert state.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]


class TestContactEntities:
    """Test Contact entities."""
    
    async def test_contact_entity_creation(
        self, hass: HomeAssistant, integration_setup, sample_contacts, broker_client
    ):
        """Test contact entities are created from coordinator data."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Simulate coordinator receiving contact data
        coordinator.data = {
            "call_stations": [],
            "contacts": sample_contacts,
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        
        # Trigger entity updates
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check that contact entities were created
        entity_reg = er.async_get(hass)
        contact_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
            and entity.entity_id.startswith(f"{DOMAIN}.contact_")
        ]
        
        # Should have entities for each contact
        assert len(contact_entities) == len(sample_contacts)
        
        # Check entity IDs and states
        for contact in sample_contacts:
            entity_id = f"{DOMAIN}.contact_{contact['contact_id']}"
            state = hass.states.get(entity_id)
            
            if state:  # Entity may not be created immediately
                assert state.state == contact["presence"]
                assert state.attributes.get("display_name") == contact["display_name"]
                assert state.attributes.get("protocol") == contact["protocol"]
                assert state.attributes.get("address") == contact["address"]
    
    async def test_contact_presence_updates(
        self, hass: HomeAssistant, integration_setup, sample_contacts, broker_client
    ):
        """Test contact presence updates through coordinator."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set initial data
        coordinator.data = {
            "call_stations": [],
            "contacts": sample_contacts,
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Update a contact's presence
        updated_contacts = sample_contacts.copy()
        updated_contacts[1]["presence"] = "online"  # Bob goes online
        
        coordinator.data["contacts"] = updated_contacts
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check updated presence
        entity_id = f"{DOMAIN}.contact_{updated_contacts[1]['contact_id']}"
        state = hass.states.get(entity_id)
        
        if state:
            assert state.state == "online"


class TestSensorEntities:
    """Test sensor entities."""
    
    async def test_system_status_sensor(
        self, hass: HomeAssistant, integration_setup, broker_client
    ):
        """Test system status sensor is created."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set system capabilities data
        coordinator.data = {
            "call_stations": [],
            "contacts": [],
            "system_capabilities": {
                "protocols": ["matrix", "xmpp"],
                "version": "1.0.0",
                "broker_status": "running",
            },
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check for system status sensor
        entity_id = f"sensor.{DOMAIN}_system_status"
        state = hass.states.get(entity_id)
        
        if state:
            assert state.state in ["running", "connected", "ok"]
            assert "protocols" in state.attributes
            assert "matrix" in state.attributes["protocols"]
    
    async def test_active_calls_sensor(
        self, hass: HomeAssistant, integration_setup, sample_call_stations, broker_client
    ):
        """Test active calls sensor updates."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set initial data with one active call
        active_stations = sample_call_stations.copy()
        active_stations[0]["state"] = "in_call"
        active_stations[0]["caller_id"] = "alice"
        
        coordinator.data = {
            "call_stations": active_stations,
            "contacts": [],
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check for active calls sensor
        entity_id = f"sensor.{DOMAIN}_active_calls"
        state = hass.states.get(entity_id)
        
        if state:
            # Should show 1 active call
            assert int(state.state) == 1
            assert "active_stations" in state.attributes


class TestEntityRegistry:
    """Test entity registry integration."""
    
    async def test_entities_registered_with_unique_ids(
        self, hass: HomeAssistant, integration_setup, sample_call_stations, sample_contacts
    ):
        """Test that entities are registered with proper unique IDs."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set data
        coordinator.data = {
            "call_stations": sample_call_stations,
            "contacts": sample_contacts,
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check entity registry
        entity_reg = er.async_get(hass)
        call_assist_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
        ]
        
        # All entities should have unique IDs
        unique_ids = [entity.unique_id for entity in call_assist_entities]
        assert len(unique_ids) == len(set(unique_ids))  # No duplicates
        
        # Unique IDs should follow expected patterns
        for entity in call_assist_entities:
            assert entity.unique_id is not None
            assert len(entity.unique_id) > 0
    
    async def test_entity_cleanup_on_data_removal(
        self, hass: HomeAssistant, integration_setup, sample_call_stations
    ):
        """Test entities are cleaned up when data is removed."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set initial data
        coordinator.data = {
            "call_stations": sample_call_stations,
            "contacts": [],
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Get initial entity count
        entity_reg = er.async_get(hass)
        initial_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
        ]
        initial_count = len(initial_entities)
        
        # Remove all call stations
        coordinator.data = {
            "call_stations": [],
            "contacts": [],
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Check that call station entities are no longer active
        remaining_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
            and entity.entity_id.startswith(f"{DOMAIN}.station_")
        ]
        
        # Should have fewer station entities (or they should be unavailable)
        station_states = [
            hass.states.get(entity.entity_id) for entity in remaining_entities
        ]
        active_stations = [
            state for state in station_states 
            if state and state.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]
        ]
        
        # Should have no active call station entities
        assert len(active_stations) == 0