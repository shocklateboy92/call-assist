#!/usr/bin/env python3
"""
Account service module for business logic related to account management.

This module handles account status checking and other business logic,
while keeping database queries separate in queries.py.
"""

import logging
from typing import Dict, Any, List

from addon.broker.queries import get_all_accounts

logger = logging.getLogger(__name__)


async def get_accounts_with_status() -> List[Dict[str, Any]]:
    """Get all accounts with real-time status check from plugins"""
    # Get plugin manager from broker
    plugin_manager = None
    try:
        # Try to get the plugin manager from the broker instance
        from addon.broker.main import get_broker_instance
        broker = get_broker_instance()
        if broker:
            plugin_manager = broker.plugin_manager
    except Exception as e:
        logger.warning(f"Could not get plugin manager: {e}")
    
    accounts = await get_all_accounts()
    accounts_with_status = []
    
    for account in accounts:
        account_dict = {
            "id": account.id,
            "protocol": account.protocol,
            "account_id": account.account_id,
            "display_name": account.display_name,
            "created_at": account.created_at.strftime("%Y-%m-%d %H:%M:%S") if account.created_at else "",
            "updated_at": account.updated_at.strftime("%Y-%m-%d %H:%M:%S") if account.updated_at else "",
        }
        
        # Check real-time status using plugin manager
        if plugin_manager:
            try:
                # Try to initialize the plugin account to check if credentials are valid
                is_valid = await plugin_manager.initialize_plugin_account(
                    protocol=account.protocol,
                    account_id=account.account_id,
                    display_name=account.display_name,
                    credentials=account.credentials
                )
                account_dict["is_valid"] = is_valid
                logger.debug(f"Account {account.account_id} status check: {'valid' if is_valid else 'invalid'}")
            except Exception as e:
                logger.error(f"Error checking status for account {account.account_id}: {e}")
                account_dict["is_valid"] = False
        else:
            # Fallback - assume invalid if plugin manager not available
            account_dict["is_valid"] = False
            logger.warning(f"Plugin manager not available, marking {account.account_id} as invalid")
        
        accounts_with_status.append(account_dict)
    
    return accounts_with_status


async def check_account_status(protocol: str, account_id: str, display_name: str, credentials: Dict[str, str]) -> bool:
    """Check the status of a single account using the plugin manager"""
    try:
        # Get plugin manager from broker
        from addon.broker.main import get_broker_instance
        broker = get_broker_instance()
        if not broker or not broker.plugin_manager:
            logger.warning("Plugin manager not available for status check")
            return False
        
        # Try to initialize the plugin account
        is_valid = await broker.plugin_manager.initialize_plugin_account(
            protocol=protocol,
            account_id=account_id,
            display_name=display_name,
            credentials=credentials
        )
        
        logger.debug(f"Account {account_id} status check: {'valid' if is_valid else 'invalid'}")
        return is_valid
        
    except Exception as e:
        logger.error(f"Error checking status for account {account_id}: {e}")
        return False