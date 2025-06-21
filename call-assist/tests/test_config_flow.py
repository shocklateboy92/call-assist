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
        self, broker_process, hass: HomeAssistant
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
