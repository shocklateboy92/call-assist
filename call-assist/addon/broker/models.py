#!/usr/bin/env python3

from sqlmodel import SQLModel, Field, create_engine, Session
from typing import Optional, Dict, Any
from datetime import datetime
import json


class Account(SQLModel, table=True):
    """SQLModel for account credentials storage"""
    id: Optional[int] = Field(default=None, primary_key=True)
    protocol: str = Field(index=True)
    account_id: str = Field(index=True)  # e.g., "@user:matrix.org"
    display_name: str
    credentials_json: str  # JSON serialized credentials
    is_valid: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_credentials(self) -> Dict[str, str]:
        """Get credentials as dictionary"""
        return json.loads(self.credentials_json) if self.credentials_json else {}
    
    def set_credentials(self, value: Dict[str, str]):
        """Set credentials from dictionary"""
        self.credentials_json = json.dumps(value)
    
    # Make credentials available as property for backward compatibility  
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_value(self) -> Any:
        """Get value as Python object"""
        return json.loads(self.value_json) if self.value_json else None
    
    def set_value(self, val: Any):
        """Set value from Python object"""
        self.value_json = json.dumps(val)
    
    # Make value available as property for backward compatibility
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
    start_time: datetime = Field(default_factory=datetime.utcnow)
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


# Database connection and session management
DATABASE_PATH = "broker_data.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables():
    """Create database and all tables"""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Get database session"""
    return Session(engine)


# Helper functions for common database operations
def get_account_by_protocol_and_id(protocol: str, account_id: str) -> Optional[Account]:
    """Get account by protocol and account_id"""
    with get_session() as session:
        return session.query(Account).filter(
            Account.protocol == protocol,
            Account.account_id == account_id
        ).first()


def get_accounts_by_protocol(protocol: str) -> list[Account]:
    """Get all accounts for a specific protocol"""
    with get_session() as session:
        return session.query(Account).filter(Account.protocol == protocol).all()


def get_all_accounts() -> list[Account]:
    """Get all accounts"""
    with get_session() as session:
        return session.query(Account).all()


def save_account(account: Account) -> Account:
    """Save or update account"""
    account.updated_at = datetime.utcnow()
    with get_session() as session:
        # Check if account already exists
        existing = session.query(Account).filter(
            Account.protocol == account.protocol,
            Account.account_id == account.account_id
        ).first()
        
        if existing:
            # Update existing account
            existing.display_name = account.display_name
            existing.credentials_json = account.credentials_json
            existing.is_valid = account.is_valid
            existing.updated_at = account.updated_at
            session.commit()
            session.refresh(existing)
            return existing
        else:
            # Create new account
            session.add(account)
            session.commit()
            session.refresh(account)
            return account


def delete_account(protocol: str, account_id: str) -> bool:
    """Delete account by protocol and account_id"""
    with get_session() as session:
        account = session.query(Account).filter(
            Account.protocol == protocol,
            Account.account_id == account_id
        ).first()
        
        if account:
            session.delete(account)
            session.commit()
            return True
        return False


def get_setting(key: str) -> Any:
    """Get setting value by key"""
    with get_session() as session:
        setting = session.query(BrokerSettings).filter(BrokerSettings.key == key).first()
        return setting.value if setting else None


def save_setting(key: str, value: Any):
    """Save or update setting"""
    with get_session() as session:
        existing = session.query(BrokerSettings).filter(BrokerSettings.key == key).first()
        
        if existing:
            existing.set_value(value)
            existing.updated_at = datetime.utcnow()
        else:
            setting = BrokerSettings(
                key=key, 
                value_json=json.dumps(value)  # Set value_json directly
            )
            session.add(setting)
        
        session.commit()


def log_call_start(call_id: str, protocol: str, account_id: str, target_address: str,
                   camera_entity_id: str, media_player_entity_id: str) -> CallLog:
    """Log the start of a call"""
    call_log = CallLog(
        call_id=call_id,
        protocol=protocol,
        account_id=account_id,
        target_address=target_address,
        camera_entity_id=camera_entity_id,
        media_player_entity_id=media_player_entity_id,
        final_state="INITIATING"
    )
    
    with get_session() as session:
        session.add(call_log)
        session.commit()
        session.refresh(call_log)
        return call_log


def log_call_end(call_id: str, final_state: str, metadata: Optional[Dict[str, Any]] = None):
    """Log the end of a call"""
    with get_session() as session:
        call_log = session.query(CallLog).filter(CallLog.call_id == call_id).first()
        if call_log:
            call_log.end_time = datetime.utcnow()
            call_log.final_state = final_state
            if metadata:
                call_log.set_metadata(metadata)
            session.commit()


def get_call_history(limit: int = 50) -> list[CallLog]:
    """Get recent call history"""
    with get_session() as session:
        return session.query(CallLog).order_by(CallLog.start_time.desc()).limit(limit).all()