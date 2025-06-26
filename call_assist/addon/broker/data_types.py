#!/usr/bin/env python3
"""
Data types module for strongly-typed internal state objects.

This module defines dataclasses to replace untyped dictionaries and Any types
throughout the broker application.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, TypedDict, Union
from datetime import datetime


@dataclass(frozen=True)
class CredentialsData:
    """Strongly typed credentials for different protocols"""
    homeserver: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    access_token: Optional[str] = None
    device_id: Optional[str] = None
    # XMPP specific
    server: Optional[str] = None
    port: Optional[int] = None
    jid: Optional[str] = None
    # Generic additional fields
    extra_fields: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class AccountStatusData:
    """Account data with status information"""
    id: Optional[int]
    protocol: str
    account_id: str
    display_name: str
    created_at: str
    updated_at: str
    is_valid: bool


@dataclass(frozen=True)
class EntityInfo:
    """Home Assistant entity information"""
    entity_id: str
    name: str
    domain: str
    available: bool


@dataclass(frozen=True)
class CallStationStatusData:
    """Call station data with availability status"""
    id: Optional[int]
    station_id: str
    display_name: str
    camera_entity_id: str
    media_player_entity_id: str
    enabled: bool
    created_at: str
    updated_at: str
    camera_available: bool
    player_available: bool
    is_available: bool
    camera_name: str
    player_name: str


@dataclass(frozen=True)
class EntityOption:
    """Entity option for form dropdowns"""
    entity_id: str
    name: str


@dataclass(frozen=True)
class AvailableEntitiesData:
    """Available entities grouped by type"""
    cameras: List[EntityOption]
    media_players: List[EntityOption]


@dataclass(frozen=True)
class ValidationErrors:
    """Validation error results"""
    camera_entity_id: Optional[str] = None
    media_player_entity_id: Optional[str] = None
    
    @property
    def has_errors(self) -> bool:
        """Check if there are any validation errors"""
        return self.camera_entity_id is not None or self.media_player_entity_id is not None
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for backward compatibility"""
        result = {}
        if self.camera_entity_id:
            result["camera_entity_id"] = self.camera_entity_id
        if self.media_player_entity_id:
            result["media_player_entity_id"] = self.media_player_entity_id
        return result


@dataclass(frozen=True)
class CallMetadata:
    """Metadata for call logs"""
    webrtc_connection_type: Optional[str] = None
    ice_connection_state: Optional[str] = None
    media_negotiation_duration_ms: Optional[int] = None
    call_end_reason: Optional[str] = None
    quality_score: Optional[float] = None
    extra_data: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class SettingsValue:
    """Typed settings value container"""
    key: str
    value: str  # JSON string
    description: Optional[str] = None


@dataclass(frozen=True)
class FieldDefinition:
    """Field definition for protocol forms"""
    name: str
    label: str
    field_type: str  # "text", "password", "url", etc.
    required: bool = True
    placeholder: Optional[str] = None
    help_text: Optional[str] = None


@dataclass(frozen=True)
class ProtocolSchema:
    """Protocol configuration schema"""
    name: str
    display_name: str
    fields: List[FieldDefinition]


class CredentialFieldDict(TypedDict):
    """TypedDict for credential field data from plugin manager"""
    key: str
    display_name: str
    description: str
    type: str
    required: bool
    default_value: str
    sensitive: bool
    allowed_values: List[str]
    placeholder: str
    validation_pattern: str


class ProtocolSchemaDict(TypedDict):
    """TypedDict for protocol schema data from plugin manager"""
    protocol: str
    display_name: str
    description: str
    credential_fields: List[CredentialFieldDict]