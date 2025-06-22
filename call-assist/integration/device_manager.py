"""Device management for Call Assist accounts."""

import logging
from typing import Dict, List, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.const import __version__ as HA_VERSION

from .const import DOMAIN
from .coordinator import CallAssistCoordinator
from .account_sensor import AccountStatusSensor, AccountCallStatusSensor

_LOGGER = logging.getLogger(__name__)


class CallAssistDeviceManager:
    """Manages devices for Call Assist accounts."""
    
    def __init__(self, hass: HomeAssistant, coordinator: CallAssistCoordinator, config_entry_id: str):
        """Initialize device manager."""
        self.hass = hass
        self.coordinator = coordinator
        self.config_entry_id = config_entry_id
        self.device_registry = dr.async_get(hass)
        self.entity_registry = er.async_get(hass)
        self.account_entities = []
        
    async def async_setup_devices(self) -> None:
        """Set up broker and account devices."""
        # Register main broker device
        broker_device = await self._register_broker_device()
        
        # Register account devices
        await self._register_account_devices(broker_device)
        
    async def _register_broker_device(self) -> dr.DeviceEntry:
        """Register the main Call Assist broker device."""
        broker_data = self.coordinator.data
        broker_version = broker_data.get("version", "unknown")
        
        device = self.device_registry.async_get_or_create(
            config_entry_id=self.config_entry_id,
            identifiers={(DOMAIN, f"broker_{self.coordinator.client.target}")},
            name="Call Assist Broker",
            manufacturer="Call Assist",
            model="Broker",
            sw_version=broker_version,
            hw_version=HA_VERSION,
            configuration_url=f"http://{self.coordinator.client.host}:{self.coordinator.client.port}",
        )
        
        _LOGGER.debug("Registered broker device: %s", device.id)
        return device
        
    async def _register_account_devices(self, broker_device: dr.DeviceEntry) -> None:
        """Register devices for each configured account."""
        if not self.coordinator.data:
            return
            
        # Get accounts from broker data
        accounts_data = await self.coordinator.client.get_configured_accounts()
        
        for account_key, account in accounts_data.items():
            await self._register_account_device(account, broker_device)
            
    async def _register_account_device(self, account: Dict[str, Any], broker_device: dr.DeviceEntry) -> dr.DeviceEntry:
        """Register a device for a specific account."""
        protocol = account.get("protocol", "unknown")
        account_id = account.get("account_id", "unknown")
        display_name = account.get("display_name", account_id)
        available = account.get("available", False)
        
        # Create unique identifier for this account
        identifier = f"{protocol}_{account_id}"
        
        device = self.device_registry.async_get_or_create(
            config_entry_id=self.config_entry_id,
            identifiers={(DOMAIN, identifier)},
            name=f"{display_name} ({protocol.title()})",
            manufacturer="Call Assist",
            model=f"{protocol.title()} Account",
            suggested_area="Communication",
            via_device=(DOMAIN, f"broker_{self.coordinator.client.target}"),
        )
        
        # Update device availability
        if not available:
            self.device_registry.async_update_device(
                device.id,
                disabled_by=dr.DeviceEntryDisabler.INTEGRATION
            )
        
        _LOGGER.debug("Registered account device: %s (%s)", display_name, identifier)
        
        # Create account sensor entities
        await self._create_account_entities(account, device)
        
        return device
        
    async def async_update_account_device(self, account: Dict[str, Any]) -> None:
        """Update an existing account device."""
        protocol = account.get("protocol", "unknown")
        account_id = account.get("account_id", "unknown")
        identifier = f"{protocol}_{account_id}"
        
        device = self.device_registry.async_get_device(
            identifiers={(DOMAIN, identifier)}
        )
        
        if device:
            display_name = account.get("display_name", account_id)
            available = account.get("available", False)
            
            # Update device name and availability
            updates = {
                "name": f"{display_name} ({protocol.title()})"
            }
            
            if not available:
                updates["disabled_by"] = dr.DeviceEntryDisabler.INTEGRATION
            else:
                updates["disabled_by"] = None
                
            self.device_registry.async_update_device(device.id, **updates)
            _LOGGER.debug("Updated account device: %s", display_name)
        
    async def async_remove_account_device(self, protocol: str, account_id: str) -> None:
        """Remove an account device."""
        identifier = f"{protocol}_{account_id}"
        
        device = self.device_registry.async_get_device(
            identifiers={(DOMAIN, identifier)}
        )
        
        if device:
            # Remove associated entities first
            entities = er.async_entries_for_device(
                self.entity_registry, 
                device.id,
                include_disabled_entities=True
            )
            
            for entity in entities:
                self.entity_registry.async_remove(entity.entity_id)
                
            # Remove the device
            self.device_registry.async_remove_device(device.id)
            _LOGGER.debug("Removed account device: %s", identifier)
            
    async def async_get_account_devices(self) -> List[dr.DeviceEntry]:
        """Get all account devices for this integration."""
        devices = []
        
        for device in self.device_registry.devices.values():
            if device.config_entry_id == self.config_entry_id:
                # Check if this is an account device (not the broker)
                for identifier_domain, identifier in device.identifiers:
                    if (identifier_domain == DOMAIN and 
                        not identifier.startswith("broker_")):
                        devices.append(device)
                        break
                        
        return devices
        
    async def async_refresh_devices(self) -> None:
        """Refresh all devices from current broker state."""
        # Re-register devices to pick up any changes
        await self.async_setup_devices()
        
    async def _create_account_entities(self, account: Dict[str, Any], device: dr.DeviceEntry) -> None:
        """Create sensor entities for an account device."""
        from homeassistant.helpers.entity_platform import async_get_platforms
        
        # Create status sensor
        status_sensor = AccountStatusSensor(self.coordinator, account, device)
        call_sensor = AccountCallStatusSensor(self.coordinator, account, device)
        
        # Store entities for potential cleanup
        self.account_entities.extend([status_sensor, call_sensor])
        
        # Register entities with the sensor platform
        # Note: This is a simplified approach. In a full implementation,
        # we'd need to integrate with the platform setup process
        _LOGGER.debug("Created account sensors for device: %s", device.name)
        
    def get_account_entities(self) -> List:
        """Get all account entities."""
        return self.account_entities