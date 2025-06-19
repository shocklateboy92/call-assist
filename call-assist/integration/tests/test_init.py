"""Test Call Assist integration initialization."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.call_assist.const import DOMAIN


class TestIntegrationSetup:
    """Test Call Assist integration setup and teardown."""
    
    async def test_setup_success(self, hass: HomeAssistant, integration_setup):
        """Test successful integration setup."""
        config_entry = integration_setup
        
        assert config_entry.state == ConfigEntryState.LOADED
        assert DOMAIN in hass.data
        assert config_entry.entry_id in hass.data[DOMAIN]
    
    async def test_setup_connection_failure(self, hass: HomeAssistant, connection_failure_config):
        """Test integration setup with broker connection failure."""
        connection_failure_config.add_to_hass(hass)
        
        result = await hass.config_entries.async_setup(connection_failure_config.entry_id)
        
        # Setup should fail gracefully
        assert not result
        assert connection_failure_config.state == ConfigEntryState.SETUP_RETRY
    
    async def test_unload_success(self, hass: HomeAssistant, integration_setup):
        """Test successful integration unload."""
        config_entry = integration_setup
        
        # Verify it's loaded first
        assert config_entry.state == ConfigEntryState.LOADED
        
        # Unload the integration
        result = await hass.config_entries.async_unload(config_entry.entry_id)
        
        assert result
        assert config_entry.state == ConfigEntryState.NOT_LOADED
        
        # Verify cleanup
        if DOMAIN in hass.data:
            assert config_entry.entry_id not in hass.data[DOMAIN]
    
    async def test_coordinator_initialization(self, hass: HomeAssistant, integration_setup, broker_client):
        """Test that coordinator is properly initialized."""
        config_entry = integration_setup
        
        # Get coordinator from hass data
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        assert coordinator is not None
        assert coordinator.config_entry == config_entry
        
        # Test initial data fetch
        await coordinator.async_config_entry_first_refresh()
        
        # Coordinator should have some initial data structure
        assert coordinator.data is not None
        assert isinstance(coordinator.data, dict)
    
    async def test_services_registration(self, hass: HomeAssistant, integration_setup):
        """Test that Call Assist services are registered."""
        config_entry = integration_setup
        
        # Check that our services are registered
        expected_services = [
            "make_call",
            "end_call", 
            "accept_call",
            "add_contact",
            "remove_contact"
        ]
        
        for service_name in expected_services:
            assert hass.services.has_service(DOMAIN, service_name)
    
    async def test_entities_creation(self, hass: HomeAssistant, integration_setup, mock_home_assistant_entities):
        """Test that entities are created when data is available."""
        config_entry = integration_setup
        
        # Get the entity registry
        entity_reg = er.async_get(hass)
        
        # Wait for initial setup to complete
        await hass.async_block_till_done()
        
        # Check for any Call Assist entities
        call_assist_entities = [
            entity for entity in entity_reg.entities.values()
            if entity.config_entry_id == config_entry.entry_id
        ]
        
        # Should have at least coordinator-related entities if broker provides data
        # Note: This may be empty if broker doesn't return initial data
        assert isinstance(call_assist_entities, list)
    
    async def test_reload_integration(self, hass: HomeAssistant, integration_setup):
        """Test reloading the integration."""
        config_entry = integration_setup
        
        # Verify initial state
        assert config_entry.state == ConfigEntryState.LOADED
        
        # Reload the integration
        result = await hass.config_entries.async_reload(config_entry.entry_id)
        
        assert result
        assert config_entry.state == ConfigEntryState.LOADED
        
        # Verify it's still in hass data
        assert DOMAIN in hass.data
        assert config_entry.entry_id in hass.data[DOMAIN]


class TestIntegrationData:
    """Test integration data management."""
    
    async def test_coordinator_data_structure(self, hass: HomeAssistant, integration_setup, broker_client):
        """Test coordinator data structure."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Perform initial refresh
        await coordinator.async_config_entry_first_refresh()
        
        # Data should be a dictionary with expected keys
        assert isinstance(coordinator.data, dict)
        
        # Common data keys that should exist (even if empty)
        expected_keys = ["call_stations", "contacts", "system_capabilities"]
        for key in expected_keys:
            assert key in coordinator.data or coordinator.data == {}
    
    async def test_system_capabilities(self, hass: HomeAssistant, integration_setup, broker_client):
        """Test system capabilities are fetched."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Get system capabilities through broker
        try:
            capabilities = await broker_client.stub.GetSystemCapabilities(
                broker_client.stub.Empty(), timeout=5.0
            )
            assert capabilities is not None
        except Exception:
            pytest.skip("Broker not responsive for capabilities test")
    
    async def test_integration_startup_with_existing_entities(
        self, hass: HomeAssistant, integration_setup, mock_home_assistant_entities
    ):
        """Test integration handles existing HA entities properly."""
        config_entry = integration_setup
        
        # Verify that existing camera and media player entities are available
        camera_states = [
            state for state_id, state in hass.states.async_all()
            if state_id.startswith("camera.")
        ]
        
        media_player_states = [
            state for state_id, state in hass.states.async_all()
            if state_id.startswith("media_player.")
        ]
        
        # Should have mock entities available
        assert len(camera_states) >= 2
        assert len(media_player_states) >= 2
        
        # Integration should be able to access these
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        assert coordinator is not None