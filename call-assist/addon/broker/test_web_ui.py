#!/usr/bin/env python3

import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlmodel import create_engine, Session, SQLModel
import tempfile
import os

from web_api import app as fastapi_app
from models import Account, BrokerSettings, CallLog
from database import DatabaseManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Create test database
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    
    # Patch the global database functions to use test database
    import models
    original_engine = models.engine
    models.engine = engine
    
    yield db_path
    
    # Cleanup
    models.engine = original_engine
    os.unlink(db_path)


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(fastapi_app)


@pytest.fixture
def sample_account(temp_db):
    """Create a sample account for testing"""
    from models import save_account
    
    account = Account(
        protocol="matrix",
        account_id="@test:matrix.org",
        display_name="Test Account",
        credentials_json='{"homeserver": "https://matrix.org", "access_token": "test_token", "user_id": "@test:matrix.org"}',
        is_valid=True
    )
    return save_account(account)


class TestWebAPI:
    """Test the FastAPI web API endpoints"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "call-assist-broker-api"
    
    def test_get_accounts_empty(self, client, temp_db):
        """Test getting accounts when none exist"""
        response = client.get("/api/accounts")
        assert response.status_code == 200
        assert response.json() == []
    
    def test_create_account(self, client, temp_db):
        """Test creating a new account"""
        account_data = {
            "protocol": "matrix",
            "account_id": "@newuser:matrix.org",
            "display_name": "New Test Account",
            "credentials": {
                "homeserver": "https://matrix.org",
                "access_token": "new_token",
                "user_id": "@newuser:matrix.org"
            }
        }
        
        response = client.post("/api/accounts", json=account_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["protocol"] == "matrix"
        assert data["account_id"] == "@newuser:matrix.org"
        assert data["display_name"] == "New Test Account"
        assert data["is_valid"] == True
    
    def test_get_account(self, client, temp_db, sample_account):
        """Test getting specific account"""
        response = client.get(f"/api/accounts/{sample_account.protocol}/{sample_account.account_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["protocol"] == sample_account.protocol
        assert data["account_id"] == sample_account.account_id
        assert data["display_name"] == sample_account.display_name
        assert "credentials" in data
    
    def test_get_nonexistent_account(self, client, temp_db):
        """Test getting account that doesn't exist"""
        response = client.get("/api/accounts/matrix/@notfound:matrix.org")
        assert response.status_code == 404
    
    def test_update_account(self, client, temp_db, sample_account):
        """Test updating existing account"""
        update_data = {
            "display_name": "Updated Test Account",
            "is_valid": False
        }
        
        response = client.put(
            f"/api/accounts/{sample_account.protocol}/{sample_account.account_id}",
            json=update_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["display_name"] == "Updated Test Account"
        assert data["is_valid"] == False
    
    def test_delete_account(self, client, temp_db, sample_account):
        """Test deleting account"""
        response = client.delete(f"/api/accounts/{sample_account.protocol}/{sample_account.account_id}")
        assert response.status_code == 200
        
        # Verify account is deleted
        response = client.get(f"/api/accounts/{sample_account.protocol}/{sample_account.account_id}")
        assert response.status_code == 404
    
    def test_create_duplicate_account(self, client, temp_db, sample_account):
        """Test creating account that already exists"""
        account_data = {
            "protocol": sample_account.protocol,
            "account_id": sample_account.account_id,
            "display_name": "Duplicate Account",
            "credentials": {"test": "value"}
        }
        
        response = client.post("/api/accounts", json=account_data)
        assert response.status_code == 409  # Conflict
    
    def test_get_call_history_empty(self, client, temp_db):
        """Test getting call history when none exists"""
        response = client.get("/api/call-history")
        assert response.status_code == 200
        assert response.json() == []
    
    def test_settings_api(self, client, temp_db):
        """Test settings management"""
        # Update a setting
        setting_data = {"key": "test_setting", "value": "test_value"}
        response = client.put("/api/settings", json=setting_data)
        assert response.status_code == 200
        
        # Get the setting
        response = client.get("/api/settings/test_setting")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "test_setting"
        assert data["value"] == "test_value"
    
    def test_database_status(self, client, temp_db):
        """Test database status endpoint"""
        response = client.get("/api/status/database")
        assert response.status_code == 200
        
        data = response.json()
        assert "accounts" in data
        assert "call_logs" in data
        assert "settings" in data
        assert "database_size_mb" in data
        assert "database_path" in data


class TestDatabaseModels:
    """Test database models and operations"""
    
    def test_account_model(self, temp_db):
        """Test Account model functionality"""
        from models import save_account, get_account_by_protocol_and_id
        
        # Create account
        account = Account(
            protocol="xmpp",
            account_id="test@jabber.org",
            display_name="XMPP Test",
            credentials_json='{"username": "test", "password": "secret", "server": "jabber.org"}',
            is_valid=True
        )
        
        # Test credentials property
        account.credentials = {"username": "test", "password": "secret", "server": "jabber.org"}
        assert account.credentials["username"] == "test"
        
        # Save and retrieve
        saved_account = save_account(account)
        assert saved_account.id is not None
        
        retrieved_account = get_account_by_protocol_and_id("xmpp", "test@jabber.org")
        assert retrieved_account is not None
        assert retrieved_account.display_name == "XMPP Test"
        assert retrieved_account.credentials["username"] == "test"
    
    def test_call_log_model(self, temp_db):
        """Test CallLog model functionality"""
        from models import log_call_start, log_call_end, get_call_history
        
        # Log call start
        call_log = log_call_start(
            "test_call_123",
            "matrix",
            "@user:matrix.org",
            "@target:matrix.org",
            "camera.living_room",
            "media_player.chromecast"
        )
        
        assert call_log.call_id == "test_call_123"
        assert call_log.protocol == "matrix"
        assert call_log.final_state == "INITIATING"
        
        # Log call end
        log_call_end("test_call_123", "COMPLETED", {"duration": "120s"})
        
        # Retrieve history
        history = get_call_history(10)
        assert len(history) == 1
        assert history[0].call_id == "test_call_123"
        assert history[0].final_state == "COMPLETED"
        assert history[0].metadata["duration"] == "120s"


class TestFormGeneration:
    """Test automatic form generation functionality"""
    
    def test_form_field_creation(self):
        """Test FormField creation and validation"""
        from form_generator import FormField
        from nicegui import ui
        
        field_config = {
            "key": "test_field",
            "display_name": "Test Field",
            "description": "A test field",
            "type": "STRING",
            "required": True,
            "default_value": "",
            "sensitive": False
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
        from form_generator import BROKER_SETTINGS_SCHEMA
        
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
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        from database import DatabaseManager
        
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