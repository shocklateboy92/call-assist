#!/usr/bin/env python3
"""
Settings service module for managing broker settings with dependency injection.
"""

import logging
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from addon.broker.data_types import BrokerSettingsDict, SettingsValueType
from addon.broker.dependencies import get_database_session
from addon.broker.queries import (
    get_setting_with_session,
    save_setting_with_session,
)

logger = logging.getLogger(__name__)


class SettingsService:
    """Settings service with dependency injection"""

    def __init__(self, session: Annotated[Session, Depends(get_database_session)]):
        self.session = session

    async def get_all_settings(self) -> BrokerSettingsDict:
        """Get all current settings"""
        return {
            "web_ui_port": get_setting_with_session(self.session, "web_ui_port", 8080),
            "web_ui_host": get_setting_with_session(
                self.session, "web_ui_host", "0.0.0.0"
            ),
            "enable_call_history": get_setting_with_session(
                self.session, "enable_call_history", True
            ),
            "max_call_history_days": get_setting_with_session(
                self.session, "max_call_history_days", 30
            ),
            "auto_cleanup_logs": get_setting_with_session(
                self.session, "auto_cleanup_logs", True
            ),
        }

    async def update_settings(self, settings: dict[str, SettingsValueType]) -> bool:
        """Update settings"""
        try:
            for key, value in settings.items():
                save_setting_with_session(self.session, key, value)
            logger.info(f"Updated {len(settings)} settings")
            return True
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"Failed to update settings: {e}")
            return False

    async def get_setting(self, key: str) -> SettingsValueType | None:
        """Get a single setting value"""
        return get_setting_with_session(self.session, key)

    async def save_setting(self, key: str, value: SettingsValueType) -> bool:
        """Save a single setting"""
        try:
            save_setting_with_session(self.session, key, value)
            return True
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"Failed to save setting {key}: {e}")
            return False


# Dependency injection helper function for FastAPI routes
async def get_settings_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> SettingsService:
    """Get SettingsService with injected dependencies"""
    return SettingsService(session)
