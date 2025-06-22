"""Account status sensor entities."""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .coordinator import CallAssistCoordinator

_LOGGER = logging.getLogger(__name__)


class AccountStatusSensor(SensorEntity):
    """Sensor representing account connection status."""
    
    def __init__(
        self, 
        coordinator: CallAssistCoordinator,
        account_data: Dict[str, Any],
        device_entry: dr.DeviceEntry
    ):
        """Initialize account status sensor."""
        self.coordinator = coordinator
        self._account_data = account_data
        self._device_entry = device_entry
        
        self._protocol = account_data.get("protocol", "unknown")
        self._account_id = account_data.get("account_id", "unknown")
        self._display_name = account_data.get("display_name", self._account_id)
        
        # Set up entity attributes
        self._attr_unique_id = f"{DOMAIN}_{self._protocol}_{self._account_id}_status"
        self._attr_name = f"{self._display_name} Status"
        self._attr_icon = "mdi:account-network"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        # Link to device
        self._attr_device_info = {
            "identifiers": device_entry.identifiers,
            "name": device_entry.name,
        }
        
        # Update initial state
        self._update_state()
        
    @property
    def state(self) -> str:
        """Return current account status."""
        if self._account_data.get("available", False):
            return "connected"
        else:
            return "disconnected"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "protocol": self._protocol,
            "account_id": self._account_id,
            "display_name": self._display_name,
            "last_seen": self._account_data.get("last_seen", "Unknown"),
        }
        
        if "error_message" in self._account_data:
            attrs["error_message"] = self._account_data["error_message"]
            
        # Add capability information
        capabilities = self._account_data.get("capabilities", {})
        if capabilities:
            attrs["video_codecs"] = capabilities.get("video_codecs", [])
            attrs["audio_codecs"] = capabilities.get("audio_codecs", [])
            attrs["webrtc_support"] = capabilities.get("webrtc_support", False)
        
        return attrs
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
    
    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        
        # Listen for account updates
        signal = f"call_assist_account_{self._account_id}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_account_update)
        )
        
        # Listen for coordinator updates
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
    
    @callback
    def _handle_account_update(self, update_data: Dict[str, Any]) -> None:
        """Handle account-specific updates."""
        self._account_data.update(update_data)
        self._update_state()
        self.async_write_ha_state()
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator data updates."""
        if self.coordinator.data:
            # Find updated account data
            accounts_data = self.coordinator.data.get("available_plugins", [])
            for plugin_data in accounts_data:
                if (plugin_data.get("protocol") == self._protocol and 
                    plugin_data.get("account_id") == self._account_id):
                    self._account_data.update(plugin_data)
                    self._update_state()
                    break
        
        self.async_write_ha_state()
    
    def _update_state(self) -> None:
        """Update internal state based on account data."""
        # Update icon based on status
        if self._account_data.get("available", False):
            self._attr_icon = "mdi:account-check"
        else:
            self._attr_icon = "mdi:account-off"


class AccountCallStatusSensor(SensorEntity):
    """Sensor representing active calls for an account."""
    
    def __init__(
        self, 
        coordinator: CallAssistCoordinator,
        account_data: Dict[str, Any],
        device_entry: dr.DeviceEntry
    ):
        """Initialize account call status sensor."""
        self.coordinator = coordinator
        self._account_data = account_data
        self._device_entry = device_entry
        
        self._protocol = account_data.get("protocol", "unknown")
        self._account_id = account_data.get("account_id", "unknown")
        self._display_name = account_data.get("display_name", self._account_id)
        
        # Set up entity attributes
        self._attr_unique_id = f"{DOMAIN}_{self._protocol}_{self._account_id}_calls"
        self._attr_name = f"{self._display_name} Active Calls"
        self._attr_icon = "mdi:phone"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = "calls"
        
        # Link to device
        self._attr_device_info = {
            "identifiers": device_entry.identifiers,
            "name": device_entry.name,
        }
        
        self._active_calls = []
        
    @property
    def native_value(self) -> int:
        """Return number of active calls."""
        return len(self._active_calls)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "protocol": self._protocol,
            "account_id": self._account_id,
            "active_calls": self._active_calls,
        }
        
        if self._active_calls:
            attrs["latest_call"] = self._active_calls[-1]
        
        return attrs
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
    
    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        
        # Listen for call events
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, 
                f"call_assist_calls_{self._account_id}", 
                self._handle_call_update
            )
        )
    
    @callback
    def _handle_call_update(self, call_data: Dict[str, Any]) -> None:
        """Handle call status updates."""
        call_id = call_data.get("call_id")
        call_state = call_data.get("state")
        
        if call_state in ["ringing", "connecting", "connected"]:
            # Add or update active call
            existing_call = next(
                (call for call in self._active_calls if call["call_id"] == call_id), 
                None
            )
            
            if existing_call:
                existing_call.update(call_data)
            else:
                self._active_calls.append(call_data)
                
        elif call_state in ["ended", "failed", "cancelled"]:
            # Remove call from active list
            self._active_calls = [
                call for call in self._active_calls 
                if call.get("call_id") != call_id
            ]
        
        self.async_write_ha_state()