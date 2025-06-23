#!/usr/bin/env python3

import logging
from pathlib import Path
from sqlmodel import create_engine, Session, select
from addon.broker.models import (
    SQLModel, Account, BrokerSettings, CallLog,
    get_session, save_setting, get_setting
)

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
            
            # Run any necessary migrations or default data setup
            await self._setup_default_settings()
            
            logger.info("Database initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _setup_default_settings(self):
        """Set up default broker settings if they don't exist"""
        try:
            # Default settings
            default_settings = {
                "web_ui_port": 8080,
                "web_ui_host": "0.0.0.0",
                "enable_call_history": True,
                "max_call_history_days": 30,
                "auto_cleanup_logs": True,
            }
            
            for key, value in default_settings.items():
                existing_value = get_setting(key)
                if existing_value is None:
                    save_setting(key, value)
                    logger.info(f"Set default setting: {key} = {value}")
                    
        except Exception as e:
            logger.error(f"Failed to setup default settings: {e}")
    
    def get_session(self) -> Session:
        """Get database session"""
        return Session(self.engine)
    
    async def cleanup_old_call_logs(self, days: int = 30):
        """Clean up call logs older than specified days"""
        try:
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
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old call logs: {e}")
    
    async def get_database_stats(self) -> dict:
        """Get database statistics"""
        try:
            with self.get_session() as session:
                account_count = len(session.exec(select(Account)).all())
                call_log_count = len(session.exec(select(CallLog)).all())
                settings_count = len(session.exec(select(BrokerSettings)).all())
                
                # Database file size
                db_size_bytes = self.database_path.stat().st_size if self.database_path.exists() else 0
                db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
                
                return {
                    "accounts": account_count,
                    "call_logs": call_log_count,
                    "settings": settings_count,
                    "database_size_mb": db_size_mb,
                    "database_path": str(self.database_path.absolute())
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
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
    
    async def migrate_from_memory_accounts(self, memory_accounts: dict):
        """Migrate accounts from in-memory storage to database"""
        try:
            migrated_count = 0
            
            for account_key, account_creds in memory_accounts.items():
                # Check if account already exists in database
                existing = session.exec(
                    select(Account).where(
                        Account.protocol == account_creds.protocol,
                        Account.account_id == account_creds.account_id
                    )
                ).first()
                
                if not existing:
                    # Create new account record
                    db_account = Account(
                        protocol=account_creds.protocol,
                        account_id=account_creds.account_id,
                        display_name=account_creds.display_name,
                        credentials_json="",  # Will be set via property
                        is_valid=account_creds.is_valid
                    )
                    db_account.credentials = account_creds.credentials
                    
                    with self.get_session() as session:
                        session.add(db_account)
                        session.commit()
                        migrated_count += 1
                        
            logger.info(f"Migrated {migrated_count} accounts from memory to database")
            return migrated_count
            
        except Exception as e:
            logger.error(f"Account migration failed: {e}")
            return 0


# Global database manager instance
db_manager = DatabaseManager()


def set_database_path(path: str):
    """Set the database path for the global database manager"""
    global db_manager
    db_manager = DatabaseManager(path)


async def init_database():
    """Initialize the global database manager"""
    await db_manager.initialize()


async def get_db_stats():
    """Get database statistics"""
    return await db_manager.get_database_stats()


async def cleanup_old_logs():
    """Clean up old call logs based on settings"""
    max_days = get_setting("max_call_history_days") or 30
    auto_cleanup = get_setting("auto_cleanup_logs")
    
    if auto_cleanup:
        await db_manager.cleanup_old_call_logs(max_days)