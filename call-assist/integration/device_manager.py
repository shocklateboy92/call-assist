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

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: CallAssistCoordinator,
        config_entry_id: str,
    ):
        """Initialize device manager."""
        self.hass = hass
        self.coordinator = coordinator
        self.config_entry_id = config_entry_id
        self.device_registry = dr.async_get(hass)
        self.entity_registry = er.async_get(hass)
        self.account_entities = []
        
        # Get config entry to access stored accounts
        from homeassistant.config_entries import ConfigEntries
        self.config_entry = hass.config_entries.async_get_entry(config_entry_id)

    async def async_setup_devices(self) -> None:
        """Set up broker and account devices."""
        # Register main broker device
        broker_device = await self._register_broker_device()

        previous_devices = dr.async_entries_for_config_entry(self.device_registry, self.config_entry_id)
        _LOGGER.info("Found %d previously registered devices for config entry %s",
            len(previous_devices), self.config_entry_id
        )

        # Push stored account configurations to broker
        await self._push_accounts_to_broker()

        # Register account devices based on stored configuration
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
        """Register devices for each configured account from stored configuration."""
        # Get stored account configurations from config entry options
        stored_accounts = self._get_stored_accounts()
        
        if not stored_accounts:
            _LOGGER.debug("No stored accounts found for device registration")
            return

        for account_key, account in stored_accounts.items():
            await self._register_account_device(account, broker_device)

    async def _register_account_device(
        self, account: Dict[str, Any], broker_device: dr.DeviceEntry
    ) -> dr.DeviceEntry:
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
            # Opens the options flow for your config entry
            configuration_url=f"homeassistant://config/config_entries/options/flow_id/{self.config_entry_id}",
        )

        # Update device availability
        if not available:
            self.device_registry.async_update_device(
                device.id, disabled_by=dr.DeviceEntryDisabler.INTEGRATION
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
            name = f"{display_name} ({protocol.title()})"
            disabled_by = None if available else dr.DeviceEntryDisabler.INTEGRATION

            self.device_registry.async_update_device(
                device.id, 
                name=name,
                disabled_by=disabled_by
            )
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
                self.entity_registry, device.id, include_disabled_entities=True
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
            if self.config_entry_id in device.config_entries:
                # Check if this is an account device (not the broker)
                for identifier_domain, identifier in device.identifiers:
                    if identifier_domain == DOMAIN and not identifier.startswith(
                        "broker_"
                    ):
                        devices.append(device)
                        break

        return devices

    async def async_refresh_devices(self) -> None:
        """Refresh all devices from stored configuration."""
        # Push accounts to broker first
        await self._push_accounts_to_broker()
        
        # Re-register devices to pick up any changes
        broker_device = await self._register_broker_device()
        await self._register_account_devices(broker_device)

    async def _create_account_entities(
        self, account: Dict[str, Any], device: dr.DeviceEntry
    ) -> None:
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

    def _get_stored_accounts(self) -> Dict[str, Any]:
        """Get stored account configurations from config entry options."""
        if not self.config_entry or not self.config_entry.options:
            return {}
        
        accounts = self.config_entry.options.get("accounts", {})
        _LOGGER.debug("Retrieved %d stored accounts from config entry", len(accounts))
        return accounts

    async def _push_accounts_to_broker(self) -> None:
        """Push stored account configurations to the broker."""
        stored_accounts = self._get_stored_accounts()
        
        if not stored_accounts:
            _LOGGER.debug("No stored accounts to push to broker")
            return
        
        success_count = 0
        for account_key, account in stored_accounts.items():
            try:
                protocol = account.get("protocol")
                account_id = account.get("account_id")
                display_name = account.get("display_name", account_id)
                credentials = account.get("credentials", {})
                
                if not protocol or not account_id or not credentials:
                    _LOGGER.warning("Skipping incomplete account configuration: %s", account_key)
                    continue
                
                success = await self.coordinator.client.add_account(
                    protocol=protocol,
                    account_id=account_id,
                    display_name=display_name,
                    credentials=credentials
                )
                
                if success:
                    success_count += 1
                    _LOGGER.debug("Successfully pushed account %s to broker", account_key)
                else:
                    _LOGGER.warning("Failed to push account %s to broker", account_key)
                    
            except Exception as ex:
                _LOGGER.error("Error pushing account %s to broker: %s", account_key, ex)
        
        _LOGGER.info("Successfully pushed %d/%d accounts to broker", success_count, len(stored_accounts))

    async def async_store_account(self, protocol: str, account_id: str, display_name: str, credentials: Dict[str, str]) -> bool:
        """Store an account configuration in config entry options."""
        if not self.config_entry:
            _LOGGER.error("Cannot store account: config entry not available")
            return False
        
        # Get current accounts
        current_options = dict(self.config_entry.options) if self.config_entry.options else {}
        accounts = current_options.get("accounts", {})
        
        # Create account key
        account_key = f"{protocol}_{account_id}"
        
        # Store account configuration
        accounts[account_key] = {
            "protocol": protocol,
            "account_id": account_id,
            "display_name": display_name,
            "credentials": credentials,
            "available": True  # Assume available when added
        }
        
        # Update config entry options
        current_options["accounts"] = accounts
        
        # Update the config entry
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options=current_options
        )
        
        _LOGGER.info("Stored account configuration: %s", account_key)
        return True

    async def async_remove_stored_account(self, protocol: str, account_id: str) -> bool:
        """Remove an account configuration from config entry options."""
        if not self.config_entry:
            _LOGGER.error("Cannot remove account: config entry not available")
            return False
        
        # Get current accounts
        current_options = dict(self.config_entry.options) if self.config_entry.options else {}
        accounts = current_options.get("accounts", {})
        
        # Create account key
        account_key = f"{protocol}_{account_id}"
        
        if account_key not in accounts:
            _LOGGER.warning("Account %s not found in stored configuration", account_key)
            return False
        
        # Remove account
        del accounts[account_key]
        
        # Update config entry options
        current_options["accounts"] = accounts
        
        # Update the config entry
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options=current_options
        )
        
        _LOGGER.info("Removed stored account configuration: %s", account_key)
        return True

    async def async_push_accounts_to_broker_on_reconnect(self) -> None:
        """Push accounts to broker after reconnection. Called by coordinator."""
        _LOGGER.info("Pushing stored accounts to broker after reconnection")
        await self._push_accounts_to_broker()