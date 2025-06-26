#!/usr/bin/env python3

import logging
from pathlib import Path
from typing import Optional
from sqlmodel import create_engine, Session, select
from addon.broker.models import SQLModel, Account, BrokerSettings, CallLog, CallStation
from addon.broker.queries import get_setting_with_session, save_setting_with_session

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database initialization and common operations"""

    def __init__(self, database_path: str = "broker_data.db"):
        self.database_path = Path(database_path)
        self.database_url = f"sqlite:///{database_path}"
        self.engine = create_engine(self.database_url, echo=False)

    async def initialize(self):
        """Initialize database and create tables if they don't exist"""
        try:
            logger.info(f"Initializing database at {self.database_path}")

            # Create all tables
            SQLModel.metadata.create_all(self.engine)

            # Run default data setup
            await self._setup_default_settings()

            logger.info("Database initialization completed successfully")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    async def _setup_default_settings(self):
        """Set up default broker settings if they don't exist"""
        # Default settings
        default_settings = {
            "web_ui_port": 8080,
            "web_ui_host": "0.0.0.0",
            "enable_call_history": True,
            "max_call_history_days": 30,
            "auto_cleanup_logs": True,
        }

        with self.get_session() as session:
            for key, value in default_settings.items():
                existing_value = get_setting_with_session(session, key)
                if existing_value is None:
                    save_setting_with_session(session, key, value)
                    logger.info(f"Set default setting: {key} = {value}")

    def get_session(self) -> Session:
        """Get database session"""
        return Session(self.engine)

    async def cleanup_old_call_logs(self, days: int = 30):
        """Clean up call logs older than specified days"""
        from datetime import datetime, timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with self.get_session() as session:
            # Delete old call logs
            old_logs = session.exec(
                select(CallLog).where(CallLog.start_time < cutoff_date)
            ).all()

            for log in old_logs:
                session.delete(log)

            session.commit()

            if old_logs:
                logger.info(f"Cleaned up {len(old_logs)} old call logs")

    async def get_database_stats(self) -> dict:
        """Get database statistics"""
        with self.get_session() as session:
            account_count = len(session.exec(select(Account)).all())
            call_log_count = len(session.exec(select(CallLog)).all())
            settings_count = len(session.exec(select(BrokerSettings)).all())

            # Database file size
            db_size_bytes = (
                self.database_path.stat().st_size
                if self.database_path.exists()
                else 0
            )
            db_size_mb = round(db_size_bytes / (1024 * 1024), 2)

            return {
                "accounts": account_count,
                "call_logs": call_log_count,
                "settings": settings_count,
                "database_size_mb": db_size_mb,
                "database_path": str(self.database_path.absolute()),
            }

    async def backup_database(self, backup_path: str) -> bool:
        """Create a backup of the database"""
        try:
            import shutil

            if not self.database_path.exists():
                logger.warning("Database file does not exist, nothing to backup")
                return False

            backup_file = Path(backup_path)
            backup_file.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(self.database_path, backup_file)
            logger.info(f"Database backed up to {backup_file}")
            return True

        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return False

    async def restore_database(self, backup_path: str) -> bool:
        """Restore database from backup"""
        try:
            import shutil

            backup_file = Path(backup_path)
            if not backup_file.exists():
                logger.error(f"Backup file does not exist: {backup_file}")
                return False

            # Stop any active connections
            self.engine.dispose()

            # Replace database file
            shutil.copy2(backup_file, self.database_path)

            # Recreate engine
            self.engine = create_engine(self.database_url, echo=False)

            logger.info(f"Database restored from {backup_file}")
            return True

        except Exception as e:
            logger.error(f"Database restore failed: {e}")
            return False
