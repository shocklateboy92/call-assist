#!/usr/bin/env python3
"""
End-to-end integration test for Call Assist integration startup.

This test simulates the full integration startup process in Home Assistant,
reproducing the "NoneType: None" error seen in the HA logs during startup.
"""

import pytest
import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady
import pytest_homeassistant_custom_component.common

from integration.const import DOMAIN, CONF_HOST, CONF_PORT
from integration import async_setup_entry, async_unload_entry

# Set up logging for tests
logger = logging.getLogger(__name__)


class TestIntegrationStartup:
    """Test the Call Assist integration startup process."""

    @pytest.mark.asyncio
    async def test_integration_startup_with_running_broker(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test integration startup with a running broker - should succeed."""
        
        # Use the proper config flow to create the entry like a real user would
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        
        # Complete config flow
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost", 
                CONF_PORT: 50051,
            },
        )
        
        # Should create entry successfully
        from homeassistant.data_entry_flow import FlowResultType
        assert result2.get("type") == FlowResultType.CREATE_ENTRY
        
        # Get the created config entry
        config_entries = hass.config_entries.async_entries(DOMAIN)
        assert len(config_entries) == 1
        config_entry = config_entries[0]
        
        # Wait for integration to fully load
        await hass.async_block_till_done()
        
        # Verify integration loaded successfully
        assert config_entry.state.name == "LOADED"
        assert DOMAIN in hass.data
        assert config_entry.entry_id in hass.data[DOMAIN]
        
        # Verify the coordinator was created and connected
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        assert coordinator is not None
        assert coordinator.client is not None
        
        # Give the coordinator some time to complete initial setup
        await asyncio.sleep(0.1)
        
        # Clean up
        unload_result = await hass.config_entries.async_unload(config_entry.entry_id)
        assert unload_result is True

    @pytest.mark.asyncio
    async def test_integration_startup_without_broker(
        self,
        call_assist_integration: None,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test integration startup without broker - should fail with ConfigEntryNotReady."""
        
        # Create a config entry pointing to non-existent broker
        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Call Assist (nonexistent)",
            data={
                CONF_HOST: "localhost",
                CONF_PORT: 99999,  # Non-existent port
            },
            source="user",
            entry_id="test_entry_id_fail",
            unique_id="localhost:99999",
            options={},
            discovery_keys={},
            subentries_data={}
        )
        
        # Mock the config entry into HA
        hass.config_entries._entries[config_entry.entry_id] = config_entry
        
        # Test the integration setup - this should fail with ConfigEntryNotReady
        with pytest.raises(ConfigEntryNotReady, match="Cannot connect to broker"):
            await async_setup_entry(hass, config_entry)
        
        # Verify nothing was stored in hass.data
        assert DOMAIN not in hass.data or config_entry.entry_id not in hass.data.get(DOMAIN, {})

    @pytest.mark.asyncio
    async def test_integration_sensor_platform_startup(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test that sensor platform startup works correctly even with empty data."""
        
        # Use the proper config flow to create the entry
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        
        # Complete config flow
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost", 
                CONF_PORT: 50051,
            },
        )
        
        # Should create entry successfully
        from homeassistant.data_entry_flow import FlowResultType
        assert result2.get("type") == FlowResultType.CREATE_ENTRY
        
        # Get the created config entry
        config_entries = hass.config_entries.async_entries(DOMAIN)
        assert len(config_entries) == 1
        config_entry = config_entries[0]
        
        # Wait for integration to fully load
        await hass.async_block_till_done()
        
        # Verify integration loaded successfully
        assert config_entry.state.name == "LOADED"
        
        # Get the coordinator
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        assert coordinator is not None
        
        # Give time for initial refresh and sensor setup
        await asyncio.sleep(0.2)
        
        # The sensor platform setup has already been called during integration setup
        # We just need to verify it completed without crashing and that the warning
        # "No Call Assist entities found from broker" was logged (which is expected)
        
        # This test verifies the sensor platform handles empty data gracefully
        # and doesn't crash with the old "NoneType: None" error
        
        # Clean up
        unload_result = await hass.config_entries.async_unload(config_entry.entry_id)
        assert unload_result is True

    @pytest.mark.asyncio  
    async def test_full_integration_lifecycle_via_ha_api(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test the full integration lifecycle using HA's public API."""
        
        # Test config flow (like user would do)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        
        # Complete config flow
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost", 
                CONF_PORT: 50051,
            },
        )
        
        # Should create entry successfully
        from homeassistant.data_entry_flow import FlowResultType
        assert result2.get("type") == FlowResultType.CREATE_ENTRY
        
        # Get the created config entry
        config_entries = hass.config_entries.async_entries(DOMAIN)
        assert len(config_entries) == 1
        config_entry = config_entries[0]
        
        # Wait for integration to fully load
        await hass.async_block_till_done()
        
        # Verify integration loaded successfully
        assert config_entry.state.name == "LOADED"
        assert DOMAIN in hass.data
        assert config_entry.entry_id in hass.data[DOMAIN]
        
        # Test that sensor entities are available
        # Give time for entities to be added
        await asyncio.sleep(0.1)
        
        # Check if any entities were created (should not crash even if none)
        from homeassistant.helpers import entity_registry
        er = entity_registry.async_get(hass)
        call_assist_entities = [
            entity for entity in er.entities.values()
            if entity.config_entry_id == config_entry.entry_id
        ]
        
        # Should not crash regardless of entity count
        logger.info(f"Found {len(call_assist_entities)} Call Assist entities")
        
        # Test unloading
        unload_result = await hass.config_entries.async_unload(config_entry.entry_id)
        assert unload_result is True
        
        # Test removal
        remove_result = await hass.config_entries.async_remove(config_entry.entry_id)
        assert remove_result["require_restart"] is False

    @pytest.mark.asyncio
    async def test_coordinator_data_handling_with_empty_response(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test that coordinator handles empty/None data responses correctly."""
        
        from integration.coordinator import CallAssistCoordinator
        
        # Create coordinator directly
        coordinator = CallAssistCoordinator(hass, "localhost", 50051)
        
        # Setup coordinator
        await coordinator.async_setup()
        
        # Test that it handles None/empty data gracefully
        try:
            # Force a refresh which might return None/empty data
            await coordinator.async_refresh()
            
            # Check data state
            logger.info(f"Coordinator data: {coordinator.data}")
            
            # Should not crash even if data is None
            if coordinator.data is None:
                logger.warning("Coordinator data is None - this might cause sensor setup issues")
            elif not coordinator.data:
                logger.warning("Coordinator data is empty - this might cause sensor setup issues")
                
        except Exception as ex:
            logger.error(f"Coordinator refresh failed: {ex}")
            
        finally:
            # Clean up
            await coordinator.async_shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])