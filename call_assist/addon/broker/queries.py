#!/usr/bin/env python3

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from addon.broker.models import (
    Account,
    BrokerSettings,
    CallLog,
    CallStation,
)

logger = logging.getLogger(__name__)


# Session-based query functions for dependency injection

def get_account_by_protocol_and_id_with_session(
    session: Session, protocol: str, account_id: str
) -> Account | None:
    """Get account by protocol and account_id using provided session"""
    return session.exec(
        select(Account).where(Account.protocol == protocol, Account.account_id == account_id)
    ).first()


def get_setting_with_session(session: Session, key: str) -> Any | None:
    """Get setting value using provided session"""
    setting = session.exec(select(BrokerSettings).where(BrokerSettings.key == key)).first()
    return setting.get_value() if setting else None


def save_setting_with_session(session: Session, key: str, value: Any) -> BrokerSettings:
    """Save setting value using provided session"""
    setting = session.exec(select(BrokerSettings).where(BrokerSettings.key == key)).first()

    if setting:
        setting.set_value(value)
        setting.updated_at = datetime.now(UTC)
    else:
        setting = BrokerSettings(key=key, value_json="{}")
        setting.set_value(value)
        session.add(setting)

    session.commit()
    session.refresh(setting)
    return setting


def get_accounts_by_protocol_with_session(session: Session, protocol: str) -> list[Account]:
    """Get all accounts for a specific protocol using provided session"""
    return list(session.exec(select(Account).where(Account.protocol == protocol)).all())


def get_all_accounts_with_session(session: Session) -> list[Account]:
    """Get all accounts using provided session"""
    return list(session.exec(select(Account)).all())


def save_account_with_session(session: Session, account: Account) -> Account:
    """Save or update account using provided session"""
    existing = session.exec(
        select(Account).where(
            Account.protocol == account.protocol, Account.account_id == account.account_id
        )
    ).first()

    if existing:
        existing.display_name = account.display_name
        existing.credentials_json = account.credentials_json
        existing.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(existing)
        return existing
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def delete_account_with_session(session: Session, protocol: str, account_id: str) -> bool:
    """Delete account by protocol and account_id using provided session"""
    account = session.exec(
        select(Account).where(Account.protocol == protocol, Account.account_id == account_id)
    ).first()

    if account:
        session.delete(account)
        session.commit()
        return True
    return False


def log_call_start_with_session(
    session: Session,
    call_id: str,
    protocol: str,
    account_id: str,
    target_address: str,
    camera_entity_id: str,
    media_player_entity_id: str,
) -> CallLog:
    """Log the start of a call using provided session"""
    call_log = CallLog(
        call_id=call_id,
        protocol=protocol,
        account_id=account_id,
        target_address=target_address,
        camera_entity_id=camera_entity_id,
        media_player_entity_id=media_player_entity_id,
        final_state="INITIATING",
    )

    session.add(call_log)
    session.commit()
    session.refresh(call_log)
    return call_log


def update_call_log_with_session(
    session: Session, call_id: str, final_state: str, error_message: str | None = None
) -> CallLog | None:
    """Update call log with final state using provided session"""
    call_log = session.exec(select(CallLog).where(CallLog.call_id == call_id)).first()

    if call_log:
        call_log.final_state = final_state
        call_log.end_time = datetime.now(UTC)
        if error_message:
            call_log.error_message = error_message
        session.commit()
        session.refresh(call_log)
        return call_log

    return None


def get_call_logs_with_session(session: Session) -> list[CallLog]:
    """Get all call logs using provided session"""
    from sqlmodel import desc
    return list(session.exec(select(CallLog).order_by(desc(CallLog.start_time))).all())


def get_call_log_by_id_with_session(session: Session, call_id: str) -> CallLog | None:
    """Get call log by ID using provided session"""
    return session.exec(select(CallLog).where(CallLog.call_id == call_id)).first()


# Call Station query functions

def get_call_station_by_id_with_session(
    session: Session, station_id: str
) -> CallStation | None:
    """Get call station by station_id using provided session"""
    return session.exec(
        select(CallStation).where(CallStation.station_id == station_id)
    ).first()


def get_all_call_stations_with_session(session: Session) -> list[CallStation]:
    """Get all call stations using provided session"""
    return list(session.exec(select(CallStation)).all())


def get_enabled_call_stations_with_session(session: Session) -> list[CallStation]:
    """Get all enabled call stations using provided session"""
    return list(session.exec(select(CallStation).where(CallStation.enabled == True)).all())


def save_call_station_with_session(session: Session, call_station: CallStation) -> CallStation:
    """Save or update call station using provided session"""
    existing = session.exec(
        select(CallStation).where(CallStation.station_id == call_station.station_id)
    ).first()

    if existing:
        existing.display_name = call_station.display_name
        existing.camera_entity_id = call_station.camera_entity_id
        existing.media_player_entity_id = call_station.media_player_entity_id
        existing.enabled = call_station.enabled
        existing.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(existing)
        return existing
    session.add(call_station)
    session.commit()
    session.refresh(call_station)
    return call_station


def delete_call_station_with_session(session: Session, station_id: str) -> bool:
    """Delete call station by station_id using provided session"""
    call_station = session.exec(
        select(CallStation).where(CallStation.station_id == station_id)
    ).first()

    if call_station:
        session.delete(call_station)
        session.commit()
        return True
    return False
