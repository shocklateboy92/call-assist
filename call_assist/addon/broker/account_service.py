#!/usr/bin/env python3
"""
Account service module for business logic related to account management.

This module handles account status checking and other business logic,
using dependency injection for clean separation of concerns.
"""

import logging
from typing import Dict, Any, List
from fastapi import Depends
from sqlmodel import Session

from addon.broker.dependencies import get_plugin_manager, get_database_session
from addon.broker.plugin_manager import PluginManager
from addon.broker.queries import get_all_accounts_with_session

logger = logging.getLogger(__name__)


class AccountService:
    """Account service with dependency injection"""
    
    def __init__(
        self,
        plugin_manager: PluginManager = Depends(get_plugin_manager),
        session: Session = Depends(get_database_session)
    ):
        self.plugin_manager = plugin_manager
        self.session = session

    async def get_accounts_with_status(self) -> List[Dict[str, Any]]:
        """Get all accounts with real-time status check from plugins"""
        accounts = get_all_accounts_with_session(self.session)
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
            try:
                # Try to initialize the plugin account to check if credentials are valid
                is_valid = await self.plugin_manager.initialize_plugin_account(
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
            
            accounts_with_status.append(account_dict)
        
        return accounts_with_status

    async def check_account_status(
        self, 
        protocol: str, 
        account_id: str, 
        display_name: str, 
        credentials: Dict[str, str]
    ) -> bool:
        """Check the status of a single account using the plugin manager"""
        try:
            # Try to initialize the plugin account
            is_valid = await self.plugin_manager.initialize_plugin_account(
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


# Dependency injection helper functions for FastAPI routes
async def get_account_service(
    plugin_manager: PluginManager = Depends(get_plugin_manager),
    session: Session = Depends(get_database_session)
) -> AccountService:
    """Get AccountService with injected dependencies"""
    return AccountService(plugin_manager, session)


# Use dependency injection via get_account_service() for FastAPI routes