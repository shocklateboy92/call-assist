#!/usr/bin/env python3

from sqlmodel import Session
from typing import Optional, Dict, Any
from datetime import datetime
import json

from addon.broker.models import Account, BrokerSettings, CallLog


def get_session() -> Session:
    """Get database session using the global database manager"""
    from addon.broker.database import db_manager
    return db_manager.get_session()


# Account query functions
def get_account_by_protocol_and_id(protocol: str, account_id: str) -> Optional[Account]:
    """Get account by protocol and account_id"""
    with get_session() as session:
        return (
            session.query(Account)
            .filter(Account.protocol == protocol, Account.account_id == account_id)
            .first()
        )


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
        existing = (
            session.query(Account)
            .filter(
                Account.protocol == account.protocol,
                Account.account_id == account.account_id,
            )
            .first()
        )

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
        account = (
            session.query(Account)
            .filter(Account.protocol == protocol, Account.account_id == account_id)
            .first()
        )

        if account:
            session.delete(account)
            session.commit()
            return True
        return False


# Settings query functions
def get_setting(key: str) -> Any:
    """Get setting value by key"""
    with get_session() as session:
        setting = (
            session.query(BrokerSettings).filter(BrokerSettings.key == key).first()
        )
        return setting.value if setting else None


def save_setting(key: str, value: Any):
    """Save or update setting"""
    with get_session() as session:
        existing = (
            session.query(BrokerSettings).filter(BrokerSettings.key == key).first()
        )

        if existing:
            existing.set_value(value)
            existing.updated_at = datetime.utcnow()
        else:
            setting = BrokerSettings(
                key=key, value_json=json.dumps(value)  # Set value_json directly
            )
            session.add(setting)

        session.commit()


# Call log query functions
def log_call_start(
    call_id: str,
    protocol: str,
    account_id: str,
    target_address: str,
    camera_entity_id: str,
    media_player_entity_id: str,
) -> CallLog:
    """Log the start of a call"""
    call_log = CallLog(
        call_id=call_id,
        protocol=protocol,
        account_id=account_id,
        target_address=target_address,
        camera_entity_id=camera_entity_id,
        media_player_entity_id=media_player_entity_id,
        final_state="INITIATING",
    )

    with get_session() as session:
        session.add(call_log)
        session.commit()
        session.refresh(call_log)
        return call_log


def log_call_end(
    call_id: str, final_state: str, metadata: Optional[Dict[str, Any]] = None
):
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
        return (
            session.query(CallLog)
            .order_by(CallLog.start_time.desc())
            .limit(limit)
            .all()
        )