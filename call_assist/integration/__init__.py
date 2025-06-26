"""Call Assist integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_HOST, CONF_PORT
from .coordinator import CallAssistCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Call Assist from a config entry."""

    # Setup coordinator to manage broker communication and HA entity monitoring
    coordinator = CallAssistCoordinator(
        hass, entry.data[CONF_HOST], entry.data[CONF_PORT], entry
    )

    try:
        await coordinator.async_setup()
    except Exception as ex:
        _LOGGER.error("Failed to setup Call Assist coordinator: %s", ex)
        raise ConfigEntryNotReady("Cannot setup coordinator") from ex

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

    # Setup platform for broker entities
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup services (only once for all integrations)
    if not hass.services.has_service(DOMAIN, "start_call"):
        await async_setup_services(hass)

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
        
        # Unload services if this was the last integration
        if not hass.data.get(DOMAIN):
            await async_unload_services(hass)

    _LOGGER.info("Call Assist integration unloaded")
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
