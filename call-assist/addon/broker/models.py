#!/usr/bin/env python3

from sqlmodel import SQLModel, Field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import json

class Account(SQLModel, table=True):
    """SQLModel for account credentials storage"""

    id: Optional[int] = Field(default=None, primary_key=True)
    protocol: str = Field(index=True)
    account_id: str = Field(index=True)  # e.g., "@user:matrix.org"
    display_name: str
    credentials_json: str  # JSON serialized credentials
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_credentials(self) -> Dict[str, str]:
        """Get credentials as dictionary"""
        return json.loads(self.credentials_json) if self.credentials_json else {}

    def set_credentials(self, value: Dict[str, str]):
        """Set credentials from dictionary"""
        self.credentials_json = json.dumps(value)

    @property
    def credentials(self) -> Dict[str, str]:
        return self.get_credentials()

    @credentials.setter
    def credentials(self, value: Dict[str, str]):
        self.set_credentials(value)

    @property
    def unique_key(self) -> str:
        """Generate unique key for this account"""
        return f"{self.protocol}_{hash(self.account_id)}"


class BrokerSettings(SQLModel, table=True):
    """SQLModel for broker configuration storage"""

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value_json: str  # JSON serialized value
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_value(self) -> Any:
        """Get value as Python object"""
        return json.loads(self.value_json) if self.value_json else None

    def set_value(self, val: Any):
        """Set value from Python object"""
        self.value_json = json.dumps(val)

    @property
    def value(self) -> Any:
        return self.get_value()

    @value.setter
    def value(self, val: Any):
        self.set_value(val)


class CallLog(SQLModel, table=True):
    """SQLModel for call history logging"""

    id: Optional[int] = Field(default=None, primary_key=True)
    call_id: str = Field(unique=True, index=True)
    protocol: str = Field(index=True)
    account_id: str = Field(index=True)
    target_address: str
    camera_entity_id: str
    media_player_entity_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    final_state: str  # CallState as string
    metadata_json: Optional[str] = None  # Additional call metadata

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata as dictionary"""
        return json.loads(self.metadata_json) if self.metadata_json else {}

    def set_metadata(self, value: Dict[str, Any]):
        """Set metadata from dictionary"""
        self.metadata_json = json.dumps(value) if value else None

    # Note: Removed metadata property due to SQLAlchemy conflict
    # Use get_metadata() and set_metadata() methods instead

    @property
    def duration_seconds(self) -> Optional[int]:
        """Get call duration in seconds"""
        if self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return None


