#!/usr/bin/env python3

import pytest
import asyncio
from sqlmodel import create_engine, Session, SQLModel
import tempfile
import os

from addon.broker.models import Account, BrokerSettings, CallLog
from addon.broker import database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database.set_database_path(db_path)

    yield db_path

    # Cleanup
    os.unlink(db_path)


@pytest.fixture
async def sample_account(temp_db):
    """Create a sample account for testing"""
    from addon.broker.queries import save_account

    account = Account(
        protocol="matrix",
        account_id="@test:matrix.org",
        display_name="Test Account",
        credentials_json='{"homeserver": "https://matrix.org", "access_token": "test_token", "user_id": "@test:matrix.org"}',
        is_valid=True,
    )
    return await save_account(account)


class TestDatabaseModels:
    """Test database models and operations"""

    async def test_account_model(self, temp_db):
        """Test Account model functionality"""
        from addon.broker.queries import save_account, get_account_by_protocol_and_id

        # Create account
        account = Account(
            protocol="xmpp",
            account_id="test@jabber.org",
            display_name="XMPP Test",
            credentials_json='{"username": "test", "password": "secret", "server": "jabber.org"}',
            is_valid=True,
        )

        # Test credentials property
        account.credentials = {
            "username": "test",
            "password": "secret",
            "server": "jabber.org",
        }
        assert account.credentials["username"] == "test"

        # Save and retrieve
        saved_account = await save_account(account)
        assert saved_account.id is not None

        retrieved_account = await get_account_by_protocol_and_id(
            "xmpp", "test@jabber.org"
        )
        assert retrieved_account is not None
        assert retrieved_account.display_name == "XMPP Test"
        assert retrieved_account.credentials["username"] == "test"

    async def test_call_log_model(self, temp_db):
        """Test CallLog model functionality"""
        from addon.broker.queries import log_call_start, log_call_end, get_call_history

        # Log call start
        call_log = await log_call_start(
            "test_call_123",
            "matrix",
            "@user:matrix.org",
            "@target:matrix.org",
            "camera.living_room",
            "media_player.chromecast",
        )

        assert call_log.call_id == "test_call_123"
        assert call_log.protocol == "matrix"
        assert call_log.final_state == "INITIATING"

        # Log call end
        await log_call_end("test_call_123", "COMPLETED", {"duration": "120s"})

        # Retrieve history
        history = await get_call_history(10)
        assert len(history) == 1
        assert history[0].call_id == "test_call_123"
        assert history[0].final_state == "COMPLETED"
        assert history[0].get_metadata()["duration"] == "120s"


class TestFormGeneration:
    """Test automatic form generation functionality"""

    def test_form_field_creation(self):
        """Test FormField creation and validation"""
        from addon.broker.form_generator import FormField
        from nicegui import ui

        field_config = {
            "key": "test_field",
            "display_name": "Test Field",
            "description": "A test field",
            "type": "STRING",
            "required": True,
            "default_value": "",
            "sensitive": False,
        }

        # This would normally create a UI component, but we'll mock it
        class MockComponent:
            def __init__(self):
                self.value = ""

        mock_component = MockComponent()
        form_field = FormField("test_field", field_config, mock_component)

        # Test validation
        assert not form_field.validate()  # Should fail because required field is empty
        assert len(form_field.validation_errors) == 1

        # Set value and test again
        form_field.value = "test_value"
        assert form_field.validate()  # Should pass now
        assert len(form_field.validation_errors) == 0

    def test_broker_settings_schema(self):
        """Test predefined broker settings schema"""
        from addon.broker.form_generator import BROKER_SETTINGS_SCHEMA

        assert "display_name" in BROKER_SETTINGS_SCHEMA
        assert "setting_fields" in BROKER_SETTINGS_SCHEMA

        settings = BROKER_SETTINGS_SCHEMA["setting_fields"]
        setting_keys = [field["key"] for field in settings]

        assert "web_ui_port" in setting_keys
        assert "web_ui_host" in setting_keys
        assert "enable_call_history" in setting_keys


@pytest.mark.asyncio
async def test_database_manager():
    """Test DatabaseManager functionality"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        from addon.broker.database import DatabaseManager

        db_manager = DatabaseManager(db_path)
        await db_manager.initialize()

        # Test database stats
        stats = await db_manager.get_database_stats()
        assert "accounts" in stats
        assert "call_logs" in stats
        assert stats["database_path"] == str(db_manager.database_path.absolute())

    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
