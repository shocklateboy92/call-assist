#!/usr/bin/env python3
"""
Integration test for Call Assist config flow

This test verifies the Home Assistant integration's configuration flow
by testing the config flow directly like a real user would experience.
"""

from unittest.mock import patch
import pytest
import logging

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest_homeassistant_custom_component
import pytest_homeassistant_custom_component.common

from integration.const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT
from integration.config_flow import CallAssistConfigFlow

# Set up logging for tests
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def register_config_flow():
    """Register the config flow handler."""
    from homeassistant.config_entries import HANDLERS

    HANDLERS[DOMAIN] = CallAssistConfigFlow


@pytest.fixture
def call_assist_integration(monkeypatch) -> None:
    """Update the Home Assistant configuration directory so the integration can be loaded."""
    monkeypatch.setattr(
        pytest_homeassistant_custom_component.common,
        "get_test_config_dir",
        lambda: "/workspaces/universal/call-assist/config/homeassistant",
    )


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

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {}

        # Test with valid broker connection (localhost where our test broker runs)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "localhost",
                CONF_PORT: 50051,
            },
        )

        # Should succeed and create entry
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Call Assist (localhost)"
        assert result2["data"] == {
            CONF_HOST: "localhost",
            CONF_PORT: 50051,
        }

    @pytest.mark.asyncio
    async def test_config_flow_with_invalid_broker(self, hass: HomeAssistant):
        """Test config flow with invalid broker connection."""
        # Create the config flow directly
        flow = CallAssistConfigFlow()
        flow.hass = hass

        # Test with invalid broker (non-existent port)
        user_input = {
            CONF_HOST: "localhost",
            CONF_PORT: 99999,  # Invalid port
        }

        result = await flow.async_step_user(user_input)

        # Should show form again with error
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_config_flow_default_values(self, hass: HomeAssistant):
        """Test that config flow shows default values."""
        # Create the config flow directly
        flow = CallAssistConfigFlow()
        flow.hass = hass

        # Test the initial step
        result = await flow.async_step_user()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        # Check that default values are present in the schema
        data_schema = result["data_schema"]
        assert data_schema is not None

        # Extract default values from schema
        defaults = {}
        for field in data_schema.schema:
            if hasattr(field, "default"):
                defaults[field.key] = field.default

        assert defaults.get(CONF_HOST) == DEFAULT_HOST
        assert defaults.get(CONF_PORT) == DEFAULT_PORT

    @pytest.mark.asyncio
    async def test_config_flow_duplicate_configuration(
        self, broker_process, hass: HomeAssistant
    ):
        """Test that duplicate configurations are rejected."""
        # Create the config flow directly
        flow = CallAssistConfigFlow()
        flow.hass = hass

        # First successful configuration
        user_input = {
            CONF_HOST: "localhost",
            CONF_PORT: 50051,
        }

        result = await flow.async_step_user(user_input)
        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Now try to create the same configuration again with a new flow instance
        flow2 = CallAssistConfigFlow()
        flow2.hass = hass

        result2 = await flow2.async_step_user(user_input)

        # Should be aborted due to duplicate unique_id
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "already_configured"

    @pytest.mark.asyncio
    async def test_config_flow_with_connection_timeout(self, hass: HomeAssistant):
        """Test config flow with connection timeout."""
        # Create the config flow directly
        flow = CallAssistConfigFlow()
        flow.hass = hass

        # Test with unreachable host (will timeout)
        user_input = {
            CONF_HOST: "192.0.2.1",  # TEST-NET-1 (unreachable)
            CONF_PORT: 50051,
        }

        result = await flow.async_step_user(user_input)

        # Should show form again with error
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

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
    async def test_config_flow_unique_id_generation(self, hass: HomeAssistant):
        """Test that unique IDs are generated correctly."""
        # Create the config flow directly
        flow = CallAssistConfigFlow()
        flow.hass = hass

        # Mock the unique ID setting to capture it
        unique_ids = []
        original_set_unique_id = flow.async_set_unique_id

        def capture_unique_id(unique_id):
            unique_ids.append(unique_id)
            return original_set_unique_id(unique_id)

        flow.async_set_unique_id = capture_unique_id

        # Test with valid broker
        user_input = {
            CONF_HOST: "test.example.com",
            CONF_PORT: 8080,
        }

        # This will fail validation but should still set unique_id
        await flow.async_step_user(user_input)

        # Should have generated unique ID in format "host:port"
        assert len(unique_ids) == 1
        assert unique_ids[0] == "test.example.com:8080"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
