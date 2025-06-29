#!/usr/bin/env python3

import json
from datetime import UTC, datetime
from typing import cast

from sqlmodel import Field, SQLModel


class Account(SQLModel, table=True):
    """SQLModel for account credentials storage"""

    id: int | None = Field(default=None, primary_key=True)
    protocol: str = Field(index=True)
    account_id: str = Field(index=True)  # e.g., "@user:matrix.org"
    display_name: str
    credentials_json: str  # JSON serialized credentials
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_credentials(self) -> dict[str, str]:
        """Get credentials as dictionary"""
        return json.loads(self.credentials_json) if self.credentials_json else {}

    def set_credentials(self, value: dict[str, str]) -> None:
        """Set credentials from dictionary"""
        self.credentials_json = json.dumps(value)

    @property
    def credentials(self) -> dict[str, str]:
        return self.get_credentials()

    @credentials.setter
    def credentials(self, value: dict[str, str]) -> None:
        self.set_credentials(value)

    @property
    def unique_key(self) -> str:
        """Generate unique key for this account"""
        return f"{self.protocol}_{hash(self.account_id)}"


class BrokerSettings(SQLModel, table=True):
    """SQLModel for broker configuration storage"""

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value_json: str  # JSON serialized value
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_value(self) -> str | int | float | bool | None:
        """Get value as Python object"""
        return (
            cast(str | int | float | bool | None, json.loads(self.value_json))
            if self.value_json
            else None
        )

    def set_value(self, val: str | int | float | bool | None) -> None:
        """Set value from Python object"""
        self.value_json = json.dumps(val)

    @property
    def value(self) -> str | int | float | bool | None:
        return self.get_value()

    @value.setter
    def value(self, val: str | int | float | bool | None) -> None:
        self.set_value(val)


class CallLog(SQLModel, table=True):
    """SQLModel for call history logging"""

    id: int | None = Field(default=None, primary_key=True)
    call_id: str = Field(unique=True, index=True)
    protocol: str = Field(index=True)
    account_id: str = Field(index=True)
    target_address: str
    camera_entity_id: str
    media_player_entity_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    final_state: str  # CallState as string
    metadata_json: str | None = None  # Additional call metadata

    def get_metadata(self) -> dict[str, str]:
        """Get metadata as dictionary"""
        return (
            cast(dict[str, str], json.loads(self.metadata_json))
            if self.metadata_json
            else {}
        )

    def set_metadata(self, value: dict[str, str]) -> None:
        """Set metadata from dictionary"""
        self.metadata_json = json.dumps(value) if value else None

    # Note: Removed metadata property due to SQLAlchemy conflict
    # Use get_metadata() and set_metadata() methods instead

    @property
    def duration_seconds(self) -> int | None:
        """Get call duration in seconds"""
        if self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return None


class CallStation(SQLModel, table=True):
    """SQLModel for call station configuration storage"""

    id: int | None = Field(default=None, primary_key=True)
    station_id: str = Field(unique=True, index=True)  # e.g., "living_room_station"
    display_name: str
    camera_entity_id: str = Field(index=True)  # e.g., "camera.living_room"
    media_player_entity_id: str = Field(
        index=True
    )  # e.g., "media_player.living_room_tv"
    enabled: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def unique_key(self) -> str:
        """Generate unique key for this call station"""
        return f"station_{hash(self.station_id)}"
