#!/usr/bin/env python3
"""
Test to reproduce the specific data mismatch bug causing NoneType error.

The sensor platform expects coordinator.data to contain "call_stations" and "contacts" keys,
but the grpc_client.async_get_status() returns different keys like "version", "broker_capabilities", etc.
This causes the sensor platform to find no entities and potentially crash.
"""

import pytest
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from integration.const import DOMAIN, CONF_HOST, CONF_PORT
from integration.coordinator import CallAssistCoordinator
from integration.grpc_client import CallAssistGrpcClient

# Set up logging for tests
logger = logging.getLogger(__name__)


class TestDataMismatchBug:
    """Test the specific data mismatch bug."""

    @pytest.mark.asyncio
    async def test_grpc_client_status_response_format(
        self,
        broker_process,
        hass: HomeAssistant,
    ):
        """Test what the grpc client actually returns vs what sensor platform expects."""

        # Test grpc client directly
        client = CallAssistGrpcClient("localhost", 50051)
        await client.async_connect()

        status_data = await client.async_get_status()
        logger.info(f"GRPC client returns: {status_data}")

        # Check what keys are actually present
        actual_keys = list(status_data.keys())
        expected_keys = ["call_stations", "contacts"]  # What sensor.py expects

        logger.info(f"Actual keys: {actual_keys}")
        logger.info(f"Expected keys: {expected_keys}")

        # This test documents the mismatch
        assert (
            "call_stations" not in status_data
        ), "call_stations key should not be present (this documents the bug)"
        assert (
            "contacts" not in status_data
        ), "contacts key should not be present (this documents the bug)"

        # But these are present instead
        assert "version" in status_data
        assert "broker_capabilities" in status_data
        assert "available_plugins" in status_data

        await client.async_disconnect()

    @pytest.mark.asyncio
    async def test_coordinator_data_vs_sensor_expectations(
        self,
        broker_process,
        hass: HomeAssistant,
    ):
        """Test coordinator data vs what sensor platform expects."""

        # Create coordinator
        coordinator = CallAssistCoordinator(hass, "localhost", 50051)
        await coordinator.async_setup()

        # Get coordinator data after refresh
        await coordinator.async_refresh()

        logger.info(f"Coordinator data: {coordinator.data}")

        # Test what sensor.py does with this data
        entities = []

        if coordinator.data:
            # Reproduce sensor.py logic
            call_stations = coordinator.data.get("call_stations", [])
            contacts = coordinator.data.get("contacts", [])

            logger.info(f"Found {len(call_stations)} call stations")
            logger.info(f"Found {len(contacts)} contacts")

            # This demonstrates the issue - empty lists because keys don't exist
            assert len(call_stations) == 0, "Should be empty due to key mismatch"
            assert len(contacts) == 0, "Should be empty due to key mismatch"
        else:
            logger.error("Coordinator data is None - this would cause NoneType error!")
            # This should not happen, but if it does, it would cause the NoneType error

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_sensor_platform_with_mismatched_data(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test sensor platform setup with mismatched data structure."""

        # Create config entry
        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Call Assist (localhost)",
            data={
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
            source="user",
            entry_id="test_data_mismatch",
            unique_id="localhost:50051",
            options={},
            discovery_keys={},
            subentries_data={},
        )

        hass.config_entries._entries[config_entry.entry_id] = config_entry

        # Setup integration manually to get coordinator
        from integration import async_setup_entry

        # This should not crash even with data mismatch
        try:
            result = await async_setup_entry(hass, config_entry)
            assert result is True

            # Get coordinator
            coordinator = hass.data[DOMAIN][config_entry.entry_id]

            logger.info(f"Coordinator data after setup: {coordinator.data}")

            # Test sensor setup manually
            from integration.sensor import async_setup_entry as sensor_setup

            added_entities = []

            async def mock_async_add_entities(entities, update_before_add=False):
                added_entities.extend(entities)
                logger.info(f"Sensor platform would add {len(entities)} entities")

            # This should not crash
            await sensor_setup(hass, config_entry, mock_async_add_entities)

            logger.info(f"Total entities added: {len(added_entities)}")
            assert (
                len(added_entities) == 0
            ), "Should be 0 due to data structure mismatch"

        except Exception as ex:
            logger.error(f"Integration setup failed: {ex}")
            raise
        finally:
            # Clean up
            if DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]:
                from integration import async_unload_entry

                await async_unload_entry(hass, config_entry)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
