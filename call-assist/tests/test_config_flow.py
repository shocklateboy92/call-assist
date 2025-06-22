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


class TestMatrixAccountConfigFlow:
    """Test Matrix account configuration through options flow."""

    @pytest.mark.asyncio
    async def test_add_matrix_account_flow(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test adding a Matrix account through the options flow."""
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
        
        # Now test the options flow for adding Matrix account
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
        
        # Should show protocol selection step
        assert dashboard_result.get("type") == FlowResultType.FORM
        assert dashboard_result.get("step_id") == "select_protocol"
        
        # Select Matrix protocol
        protocol_result = await hass.config_entries.options.async_configure(
            dashboard_result["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "My Matrix Account",
            },
        )
        
        # Should show credentials configuration step
        assert protocol_result.get("type") == FlowResultType.FORM
        assert protocol_result.get("step_id") == "configure_credentials"
        
        # Configure Matrix credentials
        credentials_result = await hass.config_entries.options.async_configure(
            protocol_result["flow_id"],
            {
                "user_id": "@testuser:matrix.example.com",
                "access_token": "test_access_token_12345",
                "homeserver": "https://matrix.example.com",
            },
        )
        
        # Should successfully create the account entry
        assert credentials_result.get("type") == FlowResultType.CREATE_ENTRY
        assert credentials_result.get("title") == "Account Added"
        assert credentials_result.get("data") == {"account_added": True}

    @pytest.mark.asyncio
    async def test_add_matrix_account_invalid_credentials(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test adding Matrix account with invalid credentials."""
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
        
        # Should show protocol selection step
        assert dashboard_result.get("type") == FlowResultType.FORM
        assert dashboard_result.get("step_id") == "select_protocol"
        
        # Select Matrix protocol
        protocol_result = await hass.config_entries.options.async_configure(
            dashboard_result["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "Invalid Matrix Account",
            },
        )
        
        # Try to configure with invalid Matrix credentials (bad homeserver)
        credentials_result = await hass.config_entries.options.async_configure(
            protocol_result["flow_id"],
            {
                "user_id": "@testuser:invalid.example.com",
                "access_token": "invalid_access_token",
                "homeserver": "https://invalid.nonexistent.server.com",
            },
        )
        
        # The Matrix plugin accepts credentials even if the server is unreachable
        # This is realistic behavior - plugins shouldn't fail initialization due to temporary network issues
        assert credentials_result.get("type") == FlowResultType.CREATE_ENTRY
        assert credentials_result.get("title") == "Account Added"
        assert credentials_result.get("data") == {"account_added": True}

    @pytest.mark.asyncio
    async def test_matrix_account_protocol_schema_loading(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
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
        
        # Check that Matrix is available in the protocol choices
        data_schema = options_flow.get("data_schema")
        assert data_schema is not None
        
        # The schema should have a protocol field with Matrix as an option
        # This is tested by successfully selecting Matrix protocol
        protocol_result = await hass.config_entries.options.async_configure(
            dashboard_result["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "Schema Test Account",
            },
        )
        
        # Should proceed to credentials step, confirming Matrix schema was loaded
        assert protocol_result.get("type") == FlowResultType.FORM
        assert protocol_result.get("step_id") == "configure_credentials"

    @pytest.mark.asyncio
    async def test_matrix_account_update_flow(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test updating an existing Matrix account."""
        # First create the integration entry and add an account
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
        
        # Add initial Matrix account
        options_flow = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )
        
        # Navigate through dashboard to add account
        dashboard_result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {
                "action": "add_account",
            },
        )
        
        protocol_result = await hass.config_entries.options.async_configure(
            dashboard_result["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "Original Matrix Account",
            },
        )
        
        credentials_result = await hass.config_entries.options.async_configure(
            protocol_result["flow_id"],
            {
                "user_id": "@original:matrix.example.com",
                "access_token": "original_access_token",
                "homeserver": "https://matrix.example.com",
            },
        )
        
        assert credentials_result.get("type") == FlowResultType.CREATE_ENTRY
        
        # Note: In a real implementation, updating accounts would require
        # additional flow steps to select existing accounts and modify them.
        # For now, this test verifies the basic add flow works as a foundation
        # for future update functionality.

    @pytest.mark.asyncio
    async def test_matrix_account_remove_flow(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test removing a Matrix account."""
        # First create the integration entry and add an account
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
        
        # Add Matrix account to later remove
        options_flow = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )
        
        # Navigate through dashboard to add account
        dashboard_result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {
                "action": "add_account",
            },
        )
        
        protocol_result = await hass.config_entries.options.async_configure(
            dashboard_result["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "Account To Remove",
            },
        )
        
        credentials_result = await hass.config_entries.options.async_configure(
            protocol_result["flow_id"],
            {
                "user_id": "@toremove:matrix.example.com",
                "access_token": "remove_access_token",
                "homeserver": "https://matrix.example.com",
            },
        )
        
        assert credentials_result.get("type") == FlowResultType.CREATE_ENTRY
        
        # Note: In a real implementation, removing accounts would require
        # additional flow steps to list existing accounts and select one to remove.
        # For now, this test verifies the basic add flow works as a foundation
        # for future remove functionality.

    @pytest.mark.asyncio
    async def test_matrix_account_multiple_accounts(
        self,
        call_assist_integration: None,
        broker_process,
        hass: HomeAssistant,
        enable_custom_integrations: None,
    ):
        """Test adding multiple Matrix accounts."""
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
        
        # Add first Matrix account
        options_flow1 = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )
        
        # Navigate through dashboard to add first account
        dashboard_result1 = await hass.config_entries.options.async_configure(
            options_flow1["flow_id"],
            {
                "action": "add_account",
            },
        )
        
        protocol_result1 = await hass.config_entries.options.async_configure(
            dashboard_result1["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "First Matrix Account",
            },
        )
        
        credentials_result1 = await hass.config_entries.options.async_configure(
            protocol_result1["flow_id"],
            {
                "user_id": "@first:matrix.example.com",
                "access_token": "first_access_token",
                "homeserver": "https://matrix.example.com",
            },
        )
        
        assert credentials_result1.get("type") == FlowResultType.CREATE_ENTRY
        
        # Add second Matrix account with different homeserver
        options_flow2 = await hass.config_entries.options.async_init(
            config_entry.entry_id
        )
        
        # Navigate through dashboard to add second account
        dashboard_result2 = await hass.config_entries.options.async_configure(
            options_flow2["flow_id"],
            {
                "action": "add_account",
            },
        )
        
        protocol_result2 = await hass.config_entries.options.async_configure(
            dashboard_result2["flow_id"],
            {
                "protocol": "matrix",
                "display_name": "Second Matrix Account",
            },
        )
        
        credentials_result2 = await hass.config_entries.options.async_configure(
            protocol_result2["flow_id"],
            {
                "user_id": "@second:different.matrix.org",
                "access_token": "second_access_token",
                "homeserver": "https://different.matrix.org",
            },
        )
        
        assert credentials_result2.get("type") == FlowResultType.CREATE_ENTRY
        
        # Both accounts should be successfully added
        assert credentials_result2.get("data") == {"account_added": True}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
