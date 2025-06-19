"""Test Call Assist config flow."""

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.call_assist.const import DOMAIN


class TestConfigFlow:
    """Test the Call Assist config flow."""
    
    async def test_form_user_step(self, hass: HomeAssistant, broker_manager):
        """Test we get the user form."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {}
        
        # Check that required fields are present
        schema_keys = [field.schema for field in result["data_schema"].schema]
        assert any("host" in str(key) for key in schema_keys)
        assert any("port" in str(key) for key in schema_keys)
    
    async def test_form_user_step_success(self, hass: HomeAssistant, broker_manager):
        """Test successful configuration with valid broker connection."""
        if broker_manager is None:
            pytest.skip("No broker available for connection test")
        
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        # Submit valid configuration
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "localhost",
                "port": 50051,
            },
        )
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Call Assist"
        assert result["data"] == {
            "host": "localhost", 
            "port": 50051,
        }
    
    async def test_form_user_step_connection_error(self, hass: HomeAssistant):
        """Test configuration with invalid broker connection."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        # Submit invalid configuration 
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "nonexistent-host",
                "port": 99999,
            },
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}
    
    async def test_form_user_step_invalid_port(self, hass: HomeAssistant):
        """Test configuration with invalid port."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        # Submit configuration with invalid port
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "localhost",
                "port": 99999,  # Port out of valid range or unavailable
            },
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}
    
    async def test_form_already_configured(self, hass: HomeAssistant, mock_config_entry):
        """Test we cannot configure the same host twice."""
        mock_config_entry.add_to_hass(hass)
        
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "host": "localhost",  # Same as mock_config_entry
                "port": 50051,
            },
        )
        
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestOptionsFlow:
    """Test the Call Assist options flow."""
    
    async def test_options_flow(self, hass: HomeAssistant, integration_setup):
        """Test options flow."""
        config_entry = integration_setup
        
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"
        
        # Configure options (if any are implemented)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={},
        )
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == {}


class TestConfigFlowValidation:
    """Test config flow validation logic."""
    
    async def test_validate_input_success(self, hass: HomeAssistant, broker_manager):
        """Test validation of valid input."""
        if broker_manager is None:
            pytest.skip("No broker available for validation test")
        
        from custom_components.call_assist.config_flow import CallAssistConfigFlow
        
        flow = CallAssistConfigFlow()
        flow.hass = hass
        
        user_input = {
            "host": "localhost",
            "port": 50051,
        }
        
        result = await flow._async_validate_input(user_input)
        
        assert "title" in result
        assert result["title"] == "Call Assist"
    
    async def test_validate_input_connection_error(self, hass: HomeAssistant):
        """Test validation with connection error."""
        from custom_components.call_assist.config_flow import CallAssistConfigFlow
        
        flow = CallAssistConfigFlow()
        flow.hass = hass
        
        user_input = {
            "host": "nonexistent-host",
            "port": 99999,
        }
        
        with pytest.raises(Exception) as exc_info:
            await flow._async_validate_input(user_input)
        
        # Should raise an exception that gets caught by the flow handler
        assert exc_info.value is not None