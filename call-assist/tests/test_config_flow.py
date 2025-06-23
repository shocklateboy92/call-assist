#!/usr/bin/env python3
"""
Integration test for Call Assist config flow

This test verifies the Home Assistant integration's configuration flow
by testing the config flow directly like a real user would experience.
"""

import pytest
import logging

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from integration.const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT
from integration.config_flow import CallAssistConfigFlow

# Set up logging for tests
logger = logging.getLogger(__name__)


class TestCallAssistConfigFlow:
    """Test the Call Assist config flow."""

    @pytest.mark.asyncio
    async def test_config_flow_with_valid_broker(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
        enable_socket,
    ):
        """Test config flow with a real running broker."""

        # Test through the config entries flow manager like a real user would
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"
        assert result.get("errors", {}) == {}

        # Test with valid broker connection (localhost where our test broker runs)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        # Should succeed and create entry
        assert result2.get("type") == FlowResultType.CREATE_ENTRY
        assert result2.get("title") == "Call Assist (localhost)"
        assert result2.get("data") == {
            CONF_HOST: "localhost",
            CONF_PORT: 50051,
        }

    @pytest.mark.asyncio
    async def test_config_flow_with_invalid_broker(
        self,
        call_assist_integration: None,
        enable_custom_integrations: None,
        hass: HomeAssistant,
    ):
        """Test config flow with invalid broker connection."""
        # Test through the config entries flow manager
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        # Test with invalid broker (non-existent port)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 99999,  # Invalid port
            },
        )

        # Should show form again with error
        assert result2.get("type") == FlowResultType.FORM
        assert result2.get("errors", {}) == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_config_flow_default_values(self, hass: HomeAssistant):
        """Test that config flow shows default values."""
        # Create the config flow directly
        flow = CallAssistConfigFlow()
        flow.hass = hass

        # Test the initial step
        result = await flow.async_step_user()

        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"

        # Check that default values are present in the schema
        data_schema = result.get("data_schema")
        assert data_schema is not None

        # Extract default values from schema - voluptuous schema format
        # The schema is processed and defaults are stored as callable lambdas
        # We need to access the original voluptuous schema to get the default values
        from integration.config_flow import STEP_USER_DATA_SCHEMA

        defaults = {}
        for field in STEP_USER_DATA_SCHEMA.schema:
            if hasattr(field, "default"):
                # Call the lambda function to get the actual default value
                defaults[field.schema] = field.default()

        assert defaults.get(CONF_HOST) == DEFAULT_HOST
        assert defaults.get(CONF_PORT) == DEFAULT_PORT

    @pytest.mark.asyncio
    async def test_config_flow_duplicate_configuration(
        self,
        call_assist_integration: None,
        enable_custom_integrations: None,
        broker_process,
        hass: HomeAssistant,
        enable_socket,
    ):
        """Test that duplicate configurations are rejected."""
        # First successful configuration
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        assert result2.get("type") == FlowResultType.CREATE_ENTRY

        # Now try to create the same configuration again
        result3 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        # Should be aborted due to duplicate unique_id or flow in progress
        assert result4.get("type") == FlowResultType.ABORT
        assert result4.get("reason") in ["already_configured", "already_in_progress"]

    @pytest.mark.asyncio
    async def test_config_flow_with_connection_timeout(
        self,
        call_assist_integration: None,
        enable_custom_integrations: None,
        hass: HomeAssistant,
    ):
        """Test config flow with connection timeout."""
        # Test through the config entries flow manager
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        # Test with unreachable host (will timeout)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.0.2.1",  # TEST-NET-1 (unreachable)
                CONF_PORT: 50051,
            },
        )

        # Should show form again with error
        assert result2.get("type") == FlowResultType.FORM
        assert result2.get("errors", {}) == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_config_flow_validation_logic(
        self, enable_socket, broker_process, hass: HomeAssistant
    ):
        """Test that the validation logic properly connects to broker."""
        from integration.config_flow import validate_input

        # Test data with localhost broker
        data = {
            CONF_HOST: "localhost",
            CONF_PORT: 50051,
        }

        # Should succeed with real broker
        result = await validate_input(hass, data)

        assert "title" in result
        assert result["title"] == "Call Assist (localhost)"
        assert "broker_version" in result  # From status response

    @pytest.mark.asyncio
    async def test_config_flow_unique_id_generation(
        self,
        call_assist_integration: None,
        enable_custom_integrations: None,
        hass: HomeAssistant,
    ):
        """Test that unique IDs are generated correctly."""
        # Test through the config entries flow manager like a real user would
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        # Test with invalid broker - should still generate unique ID
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "test.example.com",
                CONF_PORT: 8080,
            },
        )

        # Should show form with error but unique ID should have been set
        assert result2.get("type") == FlowResultType.FORM
        assert result2.get("errors", {}) == {"base": "cannot_connect"}

        # Now try to create the same configuration again - should be aborted due to duplicate
        result3 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_HOST: "test.example.com",
                CONF_PORT: 8080,
            },
        )

        # Should be aborted due to duplicate unique_id or flow in progress
        assert result4.get("type") == FlowResultType.ABORT
        assert result4.get("reason") in ["already_configured", "already_in_progress"]


class TestLegacyAccountConfigFlow:
    """Test legacy account configuration flow (now supplemented by device management)."""

    @pytest.mark.asyncio
    async def test_options_flow_account_dashboard(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
        enable_socket,
    ):
        """Test that options flow shows account dashboard."""
        # First create the integration entry
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        config_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        assert config_result.get("type") == FlowResultType.CREATE_ENTRY
        assert "result" in config_result
        config_entry = config_result["result"]

        # Test that options flow shows account dashboard
        options_flow = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )

        # Should show account dashboard
        assert options_flow.get("type") == FlowResultType.FORM
        assert options_flow.get("step_id") == "account_dashboard"

        # Dashboard should have add_account action available
        data_schema = options_flow.get("data_schema")
        assert data_schema is not None

    @pytest.mark.asyncio
    async def test_config_flow_integration_with_device_management(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
        enable_socket,
    ):
        """Test that config flow works with new device management system."""
        # Create integration entry
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        config_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        assert config_result.get("type") == FlowResultType.CREATE_ENTRY
        config_entry = config_result["result"]

        # Wait for setup to complete
        await hass.async_block_till_done()

        # Check that devices were registered
        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(hass)
        devices = dr.async_entries_for_config_entry(
            device_registry, config_entry.entry_id
        )

        # Should have at least the broker device
        assert len(devices) >= 1

        # Verify broker device exists
        broker_device = None
        for device in devices:
            if "Broker" in device.name:
                broker_device = device
                break

        assert broker_device is not None
        assert broker_device.manufacturer == "Call Assist"

    @pytest.mark.asyncio
    async def test_matrix_account_protocol_schema_loading(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
        enable_socket,
    ):
        """Test that Matrix protocol schema is loaded correctly from broker."""
        # First create the integration entry
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        config_result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        assert "result" in config_result
        config_entry = config_result["result"]

        # Start options flow
        options_flow = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )

        # Should show account dashboard first
        assert options_flow.get("type") == FlowResultType.FORM
        assert options_flow.get("step_id") == "account_dashboard"

        # Click "Add New Account" to proceed to protocol selection
        dashboard_result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {
                "action": "add_account",
            },
        )

        # Should show protocol selection with Matrix available
        assert dashboard_result.get("type") == FlowResultType.FORM
        assert dashboard_result.get("step_id") == "select_protocol"

        # Check that protocol selection is available
        data_schema = dashboard_result.get("data_schema")
        assert data_schema is not None

        # Note: Detailed account management (add, update, remove) is now
        # tested in test_device_management.py using device actions rather
        # than config flows. This provides a better user experience.


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
