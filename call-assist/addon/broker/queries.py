#!/usr/bin/env python3

from sqlmodel import Session, select
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import json
import logging

from addon.broker.models import Account, BrokerSettings, CallLog

logger = logging.getLogger(__name__)


async def get_session() -> Session:
    """Get database session using the global database manager"""
    # Import here to avoid circular dependency during migration
    from addon.broker.dependencies import get_database_instance
    db_manager = await get_database_instance()
    return db_manager.get_session()


# Account query functions
async def get_account_by_protocol_and_id(protocol: str, account_id: str) -> Optional[Account]:
    """Get account by protocol and account_id"""
    session = await get_session()
    with session:
        return session.exec(
            select(Account).where(Account.protocol == protocol, Account.account_id == account_id)
        ).first()


async def get_accounts_by_protocol(protocol: str) -> list[Account]:
    """Get all accounts for a specific protocol"""
    session = await get_session()
    with session:
        return list(session.exec(select(Account).where(Account.protocol == protocol)).all())


async def get_all_accounts() -> list[Account]:
    """Get all accounts"""
    session = await get_session()
    with session:
        return list(session.exec(select(Account)).all())


async def save_account(account: Account) -> Account:
    """Save or update account"""
    account.updated_at = datetime.now(timezone.utc)
    session = await get_session()
    with session:
        # Check if account already exists
        existing = session.exec(
            select(Account).where(
                Account.protocol == account.protocol,
                Account.account_id == account.account_id,
            )
        ).first()

        if existing:
            # Update existing account
            existing.display_name = account.display_name
            existing.credentials_json = account.credentials_json
            existing.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(existing)
            return existing
        else:
            # Create new account
            session.add(account)
            session.commit()
            session.refresh(account)
            return account


async def delete_account(protocol: str, account_id: str) -> bool:
    """Delete account by protocol and account_id"""
    session = await get_session()
    with session:
        account = session.exec(
            select(Account).where(Account.protocol == protocol, Account.account_id == account_id)
        ).first()

        if account:
            session.delete(account)
            session.commit()
            return True
        return False


# Settings query functions
async def get_setting(key: str) -> Any:
    """Get setting value by key"""
    session = await get_session()
    with session:
        setting = session.exec(
            select(BrokerSettings).where(BrokerSettings.key == key)
        ).first()
        return setting.value if setting else None


async def save_setting(key: str, value: Any):
    """Save or update setting"""
    session = await get_session()
    with session:
        existing = session.exec(
            select(BrokerSettings).where(BrokerSettings.key == key)
        ).first()

        if existing:
            existing.set_value(value)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            setting = BrokerSettings(
                key=key, value_json=json.dumps(value)  # Set value_json directly
            )
            session.add(setting)

        session.commit()


# Call log query functions
async def log_call_start(
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

    session = await get_session()
    with session:
        session.add(call_log)
        session.commit()
        session.refresh(call_log)
        return call_log


async def log_call_end(
    call_id: str, final_state: str, metadata: Optional[Dict[str, Any]] = None
):
    """Log the end of a call"""
    session = await get_session()
    with session:
        call_log = session.exec(
            select(CallLog).where(CallLog.call_id == call_id)
        ).first()
        if call_log:
            call_log.end_time = datetime.now(timezone.utc)
            call_log.final_state = final_state
            if metadata:
                call_log.set_metadata(metadata)
            session.commit()


async def get_call_history(limit: int = 50) -> list[CallLog]:
    """Get recent call history"""
    session = await get_session()
    with session:
        # Use proper SQLModel ordering
        from sqlmodel import desc
        return list(
            session.exec(
                select(CallLog).order_by(desc(CallLog.start_time)).limit(limit)
            ).all()
        )


