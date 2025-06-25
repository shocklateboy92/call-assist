#!/usr/bin/env python3
"""
Example of using FastAPI dependency injection for database queries

This shows how to create FastAPI route functions that use dependency injection
for database sessions and other dependencies, replacing the global query functions.
"""

from typing import List, Optional, Any
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from addon.broker.dependencies import get_database_session, get_plugin_manager, get_broker_instance
from addon.broker.models import Account, BrokerSettings, CallLog
from addon.broker.plugin_manager import PluginManager


# Example: Account management with dependency injection
async def get_account_by_id(
    protocol: str, 
    account_id: str,
    session: Session = Depends(get_database_session)
) -> Optional[Account]:
    """Get account by protocol and account_id using dependency injection"""
    return session.exec(
        select(Account).where(Account.protocol == protocol, Account.account_id == account_id)
    ).first()


async def create_account(
    account_data: dict,
    session: Session = Depends(get_database_session),
    plugin_manager: PluginManager = Depends(get_plugin_manager)
) -> Account:
    """Create new account using dependency injection"""
    
    # Validate protocol exists
    available_protocols = plugin_manager.get_available_protocols()
    if account_data["protocol"] not in available_protocols:
        raise HTTPException(
            status_code=400,
            detail=f"Protocol {account_data['protocol']} not available"
        )
    
    # Create account
    account = Account(
        protocol=account_data["protocol"],
        account_id=account_data["account_id"],
        display_name=account_data["display_name"],
        credentials_json="{}"  # Will be set via property
    )
    
    # Set credentials using the property
    account.credentials = account_data.get("credentials", {})
    
    # Save to database
    session.add(account)
    session.commit()
    session.refresh(account)
    
    return account


async def get_all_accounts(
    session: Session = Depends(get_database_session)
) -> List[Account]:
    """Get all accounts using dependency injection"""
    return list(session.exec(select(Account)).all())


async def delete_account_by_id(
    protocol: str,
    account_id: str,
    session: Session = Depends(get_database_session)
) -> bool:
    """Delete account using dependency injection"""
    account = session.exec(
        select(Account).where(Account.protocol == protocol, Account.account_id == account_id)
    ).first()
    
    if not account:
        return False
    
    session.delete(account)
    session.commit()
    return True


# Example: Settings management with dependency injection
async def get_setting_value(
    key: str,
    session: Session = Depends(get_database_session)
) -> Optional[Any]:
    """Get setting value using dependency injection"""
    setting = session.exec(select(BrokerSettings).where(BrokerSettings.key == key)).first()
    return setting.get_value() if setting else None


async def save_setting_value(
    key: str,
    value: Any,
    session: Session = Depends(get_database_session)
) -> BrokerSettings:
    """Save setting value using dependency injection"""
    setting = session.exec(select(BrokerSettings).where(BrokerSettings.key == key)).first()
    
    if setting:
        setting.set_value(value)
        setting.updated_at = datetime.now(timezone.utc)
    else:
        setting = BrokerSettings(key=key, value_json="{}")
        setting.set_value(value)
        session.add(setting)
    
    session.commit()
    session.refresh(setting)
    return setting


# Example: FastAPI route using multiple dependencies
async def broker_status_endpoint(
    broker = Depends(get_broker_instance),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
    session: Session = Depends(get_database_session)
) -> dict:
    """Get broker status using multiple dependencies"""
    
    # Get account count from database
    account_count = len(list(session.exec(select(Account)).all()))
    
    # Get available protocols from plugin manager
    protocols = plugin_manager.get_available_protocols()
    
    # Get broker information
    status = {
        "status": "running",
        "account_count": account_count,
        "available_protocols": protocols,
        "call_stations": len(getattr(broker, 'call_stations', {})),
        "uptime_seconds": (
            datetime.now(timezone.utc) - broker.startup_time
        ).total_seconds() if hasattr(broker, 'startup_time') else 0
    }
    
    return status
