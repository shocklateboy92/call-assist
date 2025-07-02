"""
Data types module for strongly-typed internal state objects.

This module defines dataclasses to replace untyped dictionaries and Any types
throughout the broker application.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict


@dataclass(frozen=True)
class CredentialsData:
    """Strongly typed credentials for different protocols"""

    homeserver: str | None = None
    username: str | None = None
    password: str | None = None
    access_token: str | None = None
    device_id: str | None = None
    # XMPP specific
    server: str | None = None
    port: int | None = None
    jid: str | None = None
    # Generic additional fields
    extra_fields: dict[str, str] | None = None


@dataclass(frozen=True)
class AccountStatusData:
    """Account data with status information"""

    id: int | None
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

    id: int | None
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

    cameras: list[EntityOption]
    media_players: list[EntityOption]


@dataclass(frozen=True)
class ValidationErrors:
    """Validation error results"""

    camera_entity_id: str | None = None
    media_player_entity_id: str | None = None

    @property
    def has_errors(self) -> bool:
        """Check if there are any validation errors"""
        return (
            self.camera_entity_id is not None or self.media_player_entity_id is not None
        )

    def to_dict(self) -> dict[str, str]:
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

    webrtc_connection_type: str | None = None
    ice_connection_state: str | None = None
    media_negotiation_duration_ms: int | None = None
    call_end_reason: str | None = None
    quality_score: float | None = None
    extra_data: dict[str, str] | None = None


@dataclass(frozen=True)
class SettingsValue:
    """Typed settings value container"""

    key: str
    value: str  # JSON string
    description: str | None = None


@dataclass(frozen=True)
class FieldDefinition:
    """Field definition for protocol forms"""

    name: str
    label: str
    field_type: str  # "text", "password", "url", etc.
    required: bool = True
    placeholder: str | None = None
    help_text: str | None = None


@dataclass(frozen=True)
class ProtocolSchema:
    """Protocol configuration schema"""

    name: str
    display_name: str
    fields: list[FieldDefinition]


class CredentialFieldDict(TypedDict):
    """TypedDict for credential field data from plugin manager"""

    key: str
    display_name: str
    description: str
    type: str
    required: bool
    default_value: str
    sensitive: bool
    allowed_values: list[str]
    placeholder: str
    validation_pattern: str


class ProtocolSchemaDict(TypedDict):
    """TypedDict for protocol schema data from plugin manager"""

    protocol: str
    display_name: str
    description: str
    credential_fields: list[CredentialFieldDict]
    setting_fields: list[CredentialFieldDict]  # Settings use same field structure
    example_account_ids: list[str]
    capabilities: dict[str, str | bool | int | float | list[str]]


@dataclass(frozen=True)
class BrokerEntityData:
    """Broker entity data with full type safety"""

    entity_id: str
    name: str
    entity_type: str  # BrokerEntityType from protobuf
    state: str
    attributes: dict[str, str]
    icon: str
    available: bool
    capabilities: list[str]
    last_updated: datetime


@dataclass(frozen=True)
class HAEntityUpdate:
    """HA entity update data for streaming to broker"""

    entity_id: str
    domain: str
    name: str
    state: str
    attributes: dict[str, str]
    available: bool
    last_updated: datetime
    ha_base_url: str


# Settings value types
SettingsValueType = str | int | bool | float


class BrokerSettingsDict(TypedDict):
    """TypedDict for broker settings"""

    web_ui_port: int
    web_ui_host: str
    enable_call_history: bool
    max_call_history_days: int
    auto_cleanup_logs: bool
