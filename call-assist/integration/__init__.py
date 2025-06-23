"""Call Assist integration for Home Assistant."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_HOST, CONF_PORT
from .coordinator import CallAssistCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]  # Custom platform for our entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Call Assist from a config entry."""

    # Setup gRPC coordinator
    coordinator = CallAssistCoordinator(
        hass, entry.data[CONF_HOST], entry.data[CONF_PORT], entry
    )

    try:
        await coordinator.async_setup()
    except Exception as ex:
        _LOGGER.error("Failed to connect to Call Assist broker: %s", ex)
        raise ConfigEntryNotReady("Cannot connect to broker") from ex

    # Register broker device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={
            (DOMAIN, f"broker_{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}")
        },
        name="Call Assist Broker",
        manufacturer="Call Assist",
        model="Broker",
        sw_version=coordinator.broker_version,
    )

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator}

    # Setup platform for entities
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Call Assist integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    # Get coordinator
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]

    # Shutdown coordinator
    await coordinator.async_shutdown()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove from data
        hass.data[DOMAIN].pop(entry.entry_id)

    _LOGGER.info("Call Assist integration unloaded")
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
