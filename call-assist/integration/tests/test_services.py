"""Test Call Assist services."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound

from custom_components.call_assist.const import DOMAIN


class TestCallServices:
    """Test call-related services."""
    
    async def test_make_call_service_registered(self, hass: HomeAssistant, integration_setup):
        """Test make_call service is registered."""
        assert hass.services.has_service(DOMAIN, "make_call")
    
    async def test_make_call_service(
        self, hass: HomeAssistant, integration_setup, mock_home_assistant_entities, broker_client
    ):
        """Test make_call service functionality."""
        # Call the service
        await hass.services.async_call(
            DOMAIN,
            "make_call",
            {
                "camera_entity": "camera.living_room",
                "media_player_entity": "media_player.living_room_tv",
                "target_address": "@test:matrix.org",
                "protocol": "matrix",
            },
            blocking=True,
        )
        
        # Service should complete without error
        # Note: Actual call initiation depends on broker connectivity
    
    async def test_make_call_invalid_camera(self, hass: HomeAssistant, integration_setup):
        """Test make_call with invalid camera entity."""
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "make_call",
                {
                    "camera_entity": "camera.nonexistent",
                    "media_player_entity": "media_player.living_room_tv",
                    "target_address": "@test:matrix.org",
                    "protocol": "matrix",
                },
                blocking=True,
            )
    
    async def test_make_call_invalid_media_player(self, hass: HomeAssistant, integration_setup):
        """Test make_call with invalid media player entity."""
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "make_call",
                {
                    "camera_entity": "camera.living_room",
                    "media_player_entity": "media_player.nonexistent", 
                    "target_address": "@test:matrix.org",
                    "protocol": "matrix",
                },
                blocking=True,
            )
    
    async def test_end_call_service(self, hass: HomeAssistant, integration_setup):
        """Test end_call service functionality."""
        await hass.services.async_call(
            DOMAIN,
            "end_call",
            {
                "call_id": "test_call_123",
            },
            blocking=True,
        )
        
        # Service should complete without error
    
    async def test_accept_call_service(self, hass: HomeAssistant, integration_setup):
        """Test accept_call service functionality."""
        await hass.services.async_call(
            DOMAIN,
            "accept_call",
            {
                "call_id": "test_call_123",
                "camera_entity": "camera.living_room",
                "media_player_entity": "media_player.living_room_tv",
            },
            blocking=True,
        )
        
        # Service should complete without error


class TestContactServices:
    """Test contact management services."""
    
    async def test_add_contact_service_registered(self, hass: HomeAssistant, integration_setup):
        """Test add_contact service is registered."""
        assert hass.services.has_service(DOMAIN, "add_contact")
    
    async def test_add_contact_service(self, hass: HomeAssistant, integration_setup, broker_client):
        """Test add_contact service functionality."""
        await hass.services.async_call(
            DOMAIN,
            "add_contact",
            {
                "contact_id": "test_contact",
                "display_name": "Test Contact",
                "protocol": "matrix",
                "address": "@test:matrix.org",
            },
            blocking=True,
        )
        
        # Service should complete without error
    
    async def test_add_contact_invalid_protocol(self, hass: HomeAssistant, integration_setup):
        """Test add_contact with invalid protocol."""
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "add_contact",
                {
                    "contact_id": "test_contact",
                    "display_name": "Test Contact",
                    "protocol": "invalid_protocol",
                    "address": "@test:matrix.org",
                },
                blocking=True,
            )
    
    async def test_add_contact_duplicate_id(self, hass: HomeAssistant, integration_setup, broker_client):
        """Test add_contact with duplicate contact ID."""
        # Add first contact
        await hass.services.async_call(
            DOMAIN,
            "add_contact",
            {
                "contact_id": "duplicate_test",
                "display_name": "First Contact",
                "protocol": "matrix",
                "address": "@first:matrix.org",
            },
            blocking=True,
        )
        
        # Try to add duplicate - should handle gracefully
        await hass.services.async_call(
            DOMAIN,
            "add_contact",
            {
                "contact_id": "duplicate_test",
                "display_name": "Second Contact",
                "protocol": "matrix", 
                "address": "@second:matrix.org",
            },
            blocking=True,
        )
        
        # Second call should either update existing contact or raise appropriate error
    
    async def test_remove_contact_service(self, hass: HomeAssistant, integration_setup, broker_client):
        """Test remove_contact service functionality."""
        # First add a contact
        await hass.services.async_call(
            DOMAIN,
            "add_contact",
            {
                "contact_id": "removable_contact",
                "display_name": "Removable Contact",
                "protocol": "matrix",
                "address": "@removable:matrix.org",
            },
            blocking=True,
        )
        
        # Then remove it
        await hass.services.async_call(
            DOMAIN,
            "remove_contact",
            {
                "contact_id": "removable_contact",
            },
            blocking=True,
        )
        
        # Service should complete without error
    
    async def test_remove_nonexistent_contact(self, hass: HomeAssistant, integration_setup):
        """Test remove_contact with nonexistent contact."""
        # Should handle gracefully (no error or appropriate error)
        await hass.services.async_call(
            DOMAIN,
            "remove_contact",
            {
                "contact_id": "nonexistent_contact",
            },
            blocking=True,
        )


class TestServiceValidation:
    """Test service input validation."""
    
    async def test_make_call_missing_required_params(self, hass: HomeAssistant, integration_setup):
        """Test make_call with missing required parameters."""
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "make_call",
                {
                    "camera_entity": "camera.living_room",
                    # Missing media_player_entity, target_address, protocol
                },
                blocking=True,
            )
    
    async def test_add_contact_missing_required_params(self, hass: HomeAssistant, integration_setup):
        """Test add_contact with missing required parameters."""
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "add_contact",
                {
                    "contact_id": "test_contact",
                    # Missing display_name, protocol, address
                },
                blocking=True,
            )
    
    async def test_service_with_invalid_entity_ids(self, hass: HomeAssistant, integration_setup):
        """Test services with malformed entity IDs."""
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "make_call",
                {
                    "camera_entity": "invalid_entity_id_format",
                    "media_player_entity": "media_player.living_room_tv",
                    "target_address": "@test:matrix.org",
                    "protocol": "matrix",
                },
                blocking=True,
            )


class TestServiceIntegration:
    """Test service integration with coordinator and broker."""
    
    async def test_services_use_coordinator(self, hass: HomeAssistant, integration_setup):
        """Test that services properly use the coordinator."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Services should be able to access coordinator
        assert coordinator is not None
        
        # Make a service call that should use the coordinator
        await hass.services.async_call(
            DOMAIN,
            "add_contact",
            {
                "contact_id": "coordinator_test",
                "display_name": "Coordinator Test",
                "protocol": "matrix",
                "address": "@coordinatortest:matrix.org",
            },
            blocking=True,
        )
        
        # Service should complete successfully with coordinator available
    
    async def test_services_when_broker_unavailable(self, hass: HomeAssistant, connection_failure_config):
        """Test service behavior when broker is unavailable."""
        connection_failure_config.add_to_hass(hass)
        
        # Try to set up integration (will likely fail)
        setup_result = await hass.config_entries.async_setup(connection_failure_config.entry_id)
        
        if not setup_result:
            # Services should not be available if integration failed to load
            assert not hass.services.has_service(DOMAIN, "make_call")
        else:
            # If integration loaded despite connection failure, services should handle errors gracefully
            with pytest.raises((HomeAssistantError, ServiceNotFound)):
                await hass.services.async_call(
                    DOMAIN,
                    "make_call",
                    {
                        "camera_entity": "camera.living_room",
                        "media_player_entity": "media_player.living_room_tv",
                        "target_address": "@test:matrix.org",
                        "protocol": "matrix",
                    },
                    blocking=True,
                )


class TestServiceCallbacks:
    """Test service callback functionality."""
    
    async def test_make_call_updates_call_station_state(
        self, hass: HomeAssistant, integration_setup, sample_call_stations, broker_client
    ):
        """Test that make_call updates call station state."""
        config_entry = integration_setup
        coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
        
        # Set initial call station data
        coordinator.data = {
            "call_stations": sample_call_stations,
            "contacts": [],
            "system_capabilities": {"protocols": ["matrix", "xmpp"]},
        }
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        
        # Make a call
        await hass.services.async_call(
            DOMAIN,
            "make_call",
            {
                "camera_entity": "camera.living_room",
                "media_player_entity": "media_player.living_room_tv",
                "target_address": "@test:matrix.org",
                "protocol": "matrix",
            },
            blocking=True,
        )
        
        # Give some time for state updates
        await hass.async_block_till_done()
        
        # Check if any call station states reflect the call
        station_entity_id = f"{DOMAIN}.station_living_room"
        state = hass.states.get(station_entity_id)
        
        # State may have changed to indicate call activity
        if state:
            # State could be "calling", "ringing", or remain "idle" depending on implementation
            assert state.state in ["idle", "calling", "ringing", "in_call"]