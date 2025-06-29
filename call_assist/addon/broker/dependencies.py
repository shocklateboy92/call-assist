#!/usr/bin/env python3
"""
Dependency injection setup for Call Assist Broker

This module defines all the dependencies used throughout the application,
using FastAPI's dependency injection system for clean separation of concerns.
"""

import logging
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from addon.broker.database import DatabaseManager
from addon.broker.plugin_manager import PluginManager

logger = logging.getLogger(__name__)

# Application state - these will be set during startup
_app_state = {
    "database_manager": None,
    "broker_instance": None,
    "plugin_manager": None,
    "db_path": "broker_data.db",
}


class AppState:
    """Container for application-wide state and dependencies"""

    def __init__(self):
        self.database_manager: DatabaseManager | None = None
        self.broker_instance = None  # Will be set to CallAssistBroker instance
        self.plugin_manager: PluginManager | None = None
        self.db_path: str = "broker_data.db"
        self._initialized = False

    async def initialize(self, db_path: str = "broker_data.db"):
        """Initialize all dependencies in the correct order"""
        if self._initialized:
            return

        logger.info("Initializing application dependencies...")

        # Set database path
        self.db_path = db_path

        # Initialize database manager
        self.database_manager = DatabaseManager(db_path)
        await self.database_manager.initialize()
        logger.info("✅ Database manager initialized")

        # Initialize plugin manager
        self.plugin_manager = PluginManager()
        logger.info("✅ Plugin manager initialized")

        self._initialized = True
        logger.info("🎉 All dependencies initialized successfully")

    def set_broker_instance(self, broker):
        """Set the broker instance after it's created"""
        self.broker_instance = broker
        logger.info("✅ Broker instance registered")

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Starting application cleanup...")

        # Shutdown plugin manager first
        if self.plugin_manager:
            try:
                await self.plugin_manager.shutdown_all()
                logger.info("✅ Plugin manager shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down plugin manager: {e}")

        # Close database connections
        if self.database_manager:
            try:
                self.database_manager.engine.dispose()
                logger.info("✅ Database connections closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")

        logger.info("🎉 Application cleanup complete")


# Global app state instance
app_state = AppState()


# Dependency functions for FastAPI
@lru_cache
def get_app_state() -> AppState:
    """Get the application state (cached)"""
    return app_state


async def get_database_manager(
    state: Annotated[AppState, Depends(get_app_state)]
) -> DatabaseManager:
    """Get the database manager dependency"""
    if state.database_manager is None:
        raise RuntimeError("Database manager not initialized. Call app_state.initialize() first.")
    return state.database_manager


async def get_database_session(
    db_manager: Annotated[DatabaseManager, Depends(get_database_manager)]
) -> AsyncGenerator[Session]:
    """Get a database session (automatically managed)"""
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


async def get_plugin_manager(
    state: Annotated[AppState, Depends(get_app_state)]
) -> PluginManager:
    """Get the plugin manager dependency"""
    if state.plugin_manager is None:
        raise RuntimeError("Plugin manager not initialized. Call app_state.initialize() first.")
    return state.plugin_manager


async def get_broker_instance(
    state: Annotated[AppState, Depends(get_app_state)]
):
    """Get the broker instance dependency"""
    if state.broker_instance is None:
        raise RuntimeError("Broker instance not set. Call app_state.set_broker_instance() first.")
    return state.broker_instance


# Dependency injection functions for FastAPI
