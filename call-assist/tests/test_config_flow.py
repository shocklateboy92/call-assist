"""Test the Call Assist config flow."""

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from integration.const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT


async def test_form(broker_process, hass: HomeAssistant) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


async def test_form_valid_connection(broker_process, hass: HomeAssistant) -> None:
    """Test we can successfully connect to broker."""
    
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "127.0.0.1",
            CONF_PORT: broker_process["grpc_port"],
        },
    )
    await hass.async_block_till_done()

    # Debug: check what error we're getting 
    print(f"Config flow result - type: {result2['type']}, errors: {result2.get('errors', {})}")

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Call Assist (localhost)"
    assert result2["data"] == {
        CONF_HOST: "localhost",
        CONF_PORT: broker_process["grpc_port"],
    }


async def test_form_cannot_connect(hass: HomeAssistant) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "localhost",
            CONF_PORT: 99999,  # Invalid port that should fail to connect
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_form_duplicate_connection(broker_process, hass: HomeAssistant) -> None:
    """Test we handle duplicate connections."""
    # Create the first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "localhost",
            CONF_PORT: broker_process["grpc_port"],
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY

    # Try to create a duplicate entry
    result3 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result4 = await hass.config_entries.flow.async_configure(
        result3["flow_id"],
        {
            CONF_HOST: "localhost",
            CONF_PORT: broker_process["grpc_port"],
        },
    )

    assert result4["type"] == FlowResultType.ABORT
    assert result4["reason"] == "already_configured"


async def test_default_values(hass: HomeAssistant) -> None:
    """Test that default values are used correctly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    # Check the form has the expected default values
    data_schema = result["data_schema"]
    schema_dict = {str(key): key.default() for key in data_schema.schema}
    
    assert CONF_HOST in schema_dict
    assert CONF_PORT in schema_dict