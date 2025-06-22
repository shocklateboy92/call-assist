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
from .device_manager import CallAssistDeviceManager
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]  # Custom platform for our entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Call Assist from a config entry."""
    
    # Setup gRPC coordinator
    coordinator = CallAssistCoordinator(
        hass, 
        entry.data[CONF_HOST], 
        entry.data[CONF_PORT]
    )
    
    try:
        await coordinator.async_setup()
    except Exception as ex:
        _LOGGER.error("Failed to connect to Call Assist broker: %s", ex)
        raise ConfigEntryNotReady("Cannot connect to broker") from ex
    
    # Create device manager
    device_manager = CallAssistDeviceManager(hass, coordinator, entry.entry_id)
    
    # Set device manager reference in coordinator for reconnection handling
    coordinator.set_device_manager(device_manager)
    
    # Setup devices
    await device_manager.async_setup_devices()
    
    # Store coordinator and device manager
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "device_manager": device_manager
    }
    
    # Setup platform for entities
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_setup_services(hass, coordinator)
    
    _LOGGER.info("Call Assist integration setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    # Get coordinator and device manager
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    
    # Shutdown coordinator
    await coordinator.async_shutdown()
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove from data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            await async_unload_services(hass)
    
    _LOGGER.info("Call Assist integration unloaded")
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)