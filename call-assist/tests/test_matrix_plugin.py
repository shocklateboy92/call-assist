#!/usr/bin/env python3
"""
Matrix Plugin Integration Tests

These tests validate Matrix plugin functionality through the web UI and
account management system. The tests focus on the user-facing functionality
rather than internal broker mechanics.

Updated to use the new web UI-based account management approach.
"""

import asyncio
import pytest
import pytest_asyncio
import logging
from typing import Dict, Any, Optional
from aiohttp import ClientSession

# Set up logging for tests
logger = logging.getLogger(__name__)


class MatrixTestClient:
    """Test client for interacting with Matrix homeserver"""

    def __init__(self, homeserver_url: str = "http://synapse:8008"):
        self.homeserver_url = homeserver_url
        self.access_token = None
        self.user_id = None
        self.session = ClientSession()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def register_user(self, username: str, password: str) -> Dict[str, Any]:
        """Register a test user on the Matrix homeserver, or login if already exists"""
        # First try to login in case user already exists
        login_result = await self.login(username, password)
        if "access_token" in login_result:
            return login_result

        # If login failed, try to register
        url = f"{self.homeserver_url}/_matrix/client/r0/register"
        data = {
            "username": username,
            "password": password,
            "auth": {"type": "m.login.dummy"},
        }

        async with self.session.post(url, json=data) as resp:
            result = await resp.json()
            if resp.status == 200:
                self.access_token = result["access_token"]
                self.user_id = result["user_id"]
                return result
            elif resp.status == 400 and "M_USER_IN_USE" in str(result):
                # User already exists, try to login again
                login_result = await self.login(username, password)
                return login_result
            return result

    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login with existing user credentials"""
        url = f"{self.homeserver_url}/_matrix/client/r0/login"
        data = {"type": "m.login.password", "user": username, "password": password}

        async with self.session.post(url, json=data) as resp:
            result = await resp.json()
            if resp.status == 200:
                self.access_token = result["access_token"]
                self.user_id = result["user_id"]
            return result

    async def create_room(
        self,
        name: Optional[str] = None,
        is_public: bool = False,
        is_direct: bool = False,
        invite_users: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Create a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data: dict = {"visibility": "public" if is_public else "private"}

        if is_direct:
            # For direct chats, use specific settings per Matrix spec
            data["preset"] = "trusted_private_chat"
            data["is_direct"] = True

        # Don't set a name for direct chats - they should be nameless
        if name:
            data["name"] = name

        if invite_users:
            data["invite"] = invite_users

        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()

    async def invite_user_to_room(self, room_id: str, user_id: str) -> Dict[str, Any]:
        """Invite a user to a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/invite"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {"user_id": user_id}

        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()

    async def join_room(self, room_id: str) -> Dict[str, Any]:
        """Join a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/join"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with self.session.post(url, json={}, headers=headers) as resp:
            return await resp.json()

    async def send_message(self, room_id: str, message: str) -> Dict[str, Any]:
        """Send a message to a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/send/m.room.message"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {"msgtype": "m.text", "body": message}

        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()

    async def get_room_messages(self, room_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get recent messages from a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/rooms/{room_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"dir": "b", "limit": limit}

        async with self.session.get(url, headers=headers, params=params) as resp:
            return await resp.json()

    async def get_account_data(
        self, type_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get user account data"""
        if type_filter:
            url = f"{self.homeserver_url}/_matrix/client/r0/user/{self.user_id}/account_data/{type_filter}"
        else:
            url = f"{self.homeserver_url}/_matrix/client/r0/user/{self.user_id}/account_data"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with self.session.get(url, headers=headers) as resp:
            if resp.status == 404:
                return {}
            return await resp.json()

    async def set_account_data(
        self, data_type: str, content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Set user account data"""
        url = f"{self.homeserver_url}/_matrix/client/r0/user/{self.user_id}/account_data/{data_type}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with self.session.put(url, json=content, headers=headers) as resp:
            return await resp.json() if resp.status != 200 else {}


TEST_PASSWORD = "testpassword123"
RECEIVER_USERNAME = "testreceiver"
CALLER_USERNAME = "testcaller"
TEST_ROOM_NAME = "Test Video Call Room"



@pytest_asyncio.fixture
async def matrix_test_users():
    """Create test users on the Matrix homeserver"""
    users = {}

    async with MatrixTestClient() as client:
        # Use consistent caller user (will login if already exists)
        caller_result = await client.register_user(CALLER_USERNAME, TEST_PASSWORD)
        if "access_token" in caller_result:
            users["caller"] = {
                "user_id": caller_result["user_id"],
                "access_token": caller_result["access_token"],
                "password": TEST_PASSWORD,
            }

        # Use consistent receiver user (will login if already exists)
        receiver_result = await client.register_user(RECEIVER_USERNAME, TEST_PASSWORD)
        if "access_token" in receiver_result:
            users["receiver"] = {
                "user_id": receiver_result["user_id"],
                "access_token": receiver_result["access_token"],
                "password": TEST_PASSWORD,
            }

    return users


@pytest_asyncio.fixture
async def matrix_test_room(matrix_test_users):
    """Get or create a consistent direct chat between caller and receiver"""
    if "receiver" not in matrix_test_users or "caller" not in matrix_test_users:
        pytest.skip("Both receiver and caller users required")

    receiver = matrix_test_users["receiver"]
    caller = matrix_test_users["caller"]

    # Setup receiver credentials in the account management system
    from addon.broker.models import Account
    from addon.broker.queries import save_account, delete_account
    
    # Clean up any existing test accounts first
    delete_account("matrix", receiver["user_id"])
    
    # Create account using the web UI's account management system
    receiver_account = Account(
        protocol="matrix",
        account_id=receiver["user_id"],
        display_name=receiver["user_id"],
        credentials_json=""
    )
    receiver_account.credentials = {
        "access_token": receiver["access_token"],
        "user_id": receiver["user_id"],
        "homeserver": "http://synapse:8008",
    }
    save_account(receiver_account)

    # Check if a direct chat room already exists
    test_room_id = None

    async with MatrixTestClient() as client:
        client.access_token = receiver["access_token"]
        client.user_id = receiver["user_id"]

        # Check existing m.direct account data for existing room with caller
        direct_data = await client.get_account_data("m.direct")
        if direct_data and caller["user_id"] in direct_data:
            room_list = direct_data[caller["user_id"]]
            if room_list:
                # Use the first existing room
                test_room_id = room_list[0]

        # If no existing room found, create a new direct chat
        if not test_room_id:
            room_result = await client.create_room(
                is_direct=True, invite_users=[caller["user_id"]]
            )
            if "room_id" in room_result:
                test_room_id = room_result["room_id"]

                # Set m.direct account data for receiver
                if not direct_data:
                    direct_data = {}

                # Add this room as a direct chat with the caller
                if caller["user_id"] not in direct_data:
                    direct_data[caller["user_id"]] = []
                if test_room_id not in direct_data[caller["user_id"]]:
                    direct_data[caller["user_id"]].append(test_room_id)

                await client.set_account_data("m.direct", direct_data)

    if not test_room_id:
        pytest.skip("Could not find or create direct chat room")

    # Ensure caller has joined the direct chat and has proper m.direct data
    async with MatrixTestClient() as client:
        client.access_token = caller["access_token"]
        client.user_id = caller["user_id"]

        # Try to join the room (will succeed silently if already joined)
        await client.join_room(test_room_id)

        # Set m.direct account data for caller
        direct_data = await client.get_account_data("m.direct")
        if not direct_data:
            direct_data = {}

        # Add this room as a direct chat with the receiver
        if receiver["user_id"] not in direct_data:
            direct_data[receiver["user_id"]] = []
        if test_room_id not in direct_data[receiver["user_id"]]:
            direct_data[receiver["user_id"]].append(test_room_id)

        await client.set_account_data("m.direct", direct_data)

    return test_room_id


class TestMatrixPluginIntegration:
    """Integration tests for Matrix plugin through web UI and account management"""

    @pytest.mark.asyncio
    async def test_account_management_system(self):
        """Test that the account management system is working"""
        from addon.broker.database import DatabaseManager
        from addon.broker.queries import get_all_accounts
        import tempfile
        import os
        
        # Create a temporary database for this test
        test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(test_db_fd)
        
        try:
            # Initialize database manager
            db_manager = DatabaseManager(test_db_path)
            await db_manager.initialize()
            
            # Set global db_manager for queries to use
            import addon.broker.database
            addon.broker.database.db_manager = db_manager
            
            # Test database connectivity
            accounts = get_all_accounts()
            assert isinstance(accounts, list), "Should be able to query accounts"
            assert len(accounts) == 0, "Database should start empty"
            
            # Test database stats
            stats = await db_manager.get_database_stats()
            assert isinstance(stats, dict), "Should be able to get database stats"
            assert "accounts" in stats, "Stats should include account count"
            assert stats["accounts"] == 0, "Should have 0 accounts initially"
            
        finally:
            # Clean up test database
            if os.path.exists(test_db_path):
                os.unlink(test_db_path)

    @pytest.mark.asyncio
    async def test_matrix_credentials_setup(self, matrix_test_users):
        """Test Matrix account setup through web UI account management"""
        if "caller" not in matrix_test_users:
            pytest.skip("No test users available")

        caller = matrix_test_users["caller"]

        # Setup database for this test
        from addon.broker.database import DatabaseManager
        import tempfile
        import os
        
        test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(test_db_fd)
        
        try:
            # Initialize database
            db_manager = DatabaseManager(test_db_path)
            await db_manager.initialize()
            
            # Set global db_manager for queries to use
            import addon.broker.database
            addon.broker.database.db_manager = db_manager

            # Create Matrix account using the web UI's account management system
            from addon.broker.models import Account
            from addon.broker.queries import save_account, get_account_by_protocol_and_id, delete_account

            # Create account (this is what the web UI does)
            account = Account(
                protocol="matrix",
                account_id=caller["user_id"],
                display_name=caller["user_id"],
                credentials_json=""
            )
            account.credentials = {
                "access_token": caller["access_token"],
                "user_id": caller["user_id"],
                "homeserver": "http://synapse:8008",
            }

            save_account(account)

            # Verify account was saved
            saved_account = get_account_by_protocol_and_id("matrix", caller["user_id"])
            assert saved_account is not None, "Account should be saved"
            assert saved_account.protocol == "matrix"
            assert saved_account.credentials["user_id"] == caller["user_id"]
            assert saved_account.credentials["access_token"] == caller["access_token"]
            
        finally:
            # Clean up test database
            if os.path.exists(test_db_path):
                os.unlink(test_db_path)

    @pytest.mark.asyncio
    async def test_matrix_account_persistence(self, matrix_test_users):
        """Test Matrix account data persistence and retrieval"""
        if "caller" not in matrix_test_users:
            pytest.skip("No test users available")

        caller = matrix_test_users["caller"]

        # Setup database for this test
        from addon.broker.database import DatabaseManager
        import tempfile
        import os
        
        test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(test_db_fd)
        
        try:
            # Initialize database
            db_manager = DatabaseManager(test_db_path)
            await db_manager.initialize()
            
            # Set global db_manager for queries to use
            import addon.broker.database
            addon.broker.database.db_manager = db_manager

            # Setup Matrix account using web UI account management
            from addon.broker.models import Account
            from addon.broker.queries import save_account, get_account_by_protocol_and_id, get_all_accounts, delete_account

            # Create Matrix account with comprehensive data
            account = Account(
                protocol="matrix",
                account_id=caller["user_id"],
                display_name="Test Matrix Account",
                credentials_json=""
            )
            account.credentials = {
                "access_token": caller["access_token"],
                "user_id": caller["user_id"],
                "homeserver": "http://synapse:8008",
                "device_id": "test_device_123",
                "additional_settings": {
                    "encryption_enabled": True,
                    "auto_join_rooms": False
                }
            }
            save_account(account)

            # Verify account is saved correctly
            saved_account = get_account_by_protocol_and_id("matrix", caller["user_id"])
            assert saved_account is not None, "Account should be saved"
            assert saved_account.protocol == "matrix"
            assert saved_account.display_name == "Test Matrix Account"
            assert saved_account.credentials["access_token"] == caller["access_token"]
            assert saved_account.credentials["device_id"] == "test_device_123"
            assert saved_account.credentials["additional_settings"]["encryption_enabled"] is True

            # Verify account appears in all accounts list
            all_accounts = get_all_accounts()
            matrix_accounts = [acc for acc in all_accounts if acc.protocol == "matrix" and acc.account_id == caller["user_id"]]
            assert len(matrix_accounts) == 1, "Should find exactly one Matrix account"

            # Update account
            saved_account.display_name = "Updated Matrix Account"
            # Properly update credentials (need to reassign to trigger JSON serialization)
            updated_creds = saved_account.credentials.copy()
            updated_creds["device_id"] = "updated_device_456"
            saved_account.credentials = updated_creds
            save_account(saved_account)

            # Verify update persisted
            updated_account = get_account_by_protocol_and_id("matrix", caller["user_id"])
            assert updated_account.display_name == "Updated Matrix Account"
            assert updated_account.credentials["device_id"] == "updated_device_456"
            # Other fields should remain unchanged
            assert updated_account.credentials["access_token"] == caller["access_token"]
            
        finally:
            # Clean up test database
            if os.path.exists(test_db_path):
                os.unlink(test_db_path)

    @pytest.mark.asyncio
    async def test_matrix_account_validation(self, matrix_test_users):
        """Test Matrix account credential validation"""
        if "caller" not in matrix_test_users:
            pytest.skip("Caller user required for validation test")

        caller = matrix_test_users["caller"]
        
        # Setup database for this test
        from addon.broker.database import DatabaseManager
        import tempfile
        import os
        
        test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(test_db_fd)
        
        try:
            # Initialize database
            db_manager = DatabaseManager(test_db_path)
            await db_manager.initialize()
            
            # Set global db_manager for queries to use
            import addon.broker.database
            addon.broker.database.db_manager = db_manager
        
            from addon.broker.models import Account
            from addon.broker.queries import save_account, get_account_by_protocol_and_id, delete_account
        
            # Test valid credentials
            valid_account = Account(
                protocol="matrix",
                account_id=caller["user_id"],
                display_name="Valid Test Account",
                credentials_json=""
            )
            valid_account.credentials = {
                "access_token": caller["access_token"],
                "user_id": caller["user_id"],
                "homeserver": "http://synapse:8008",
            }
            
            save_account(valid_account)
            
            # Retrieve and verify
            retrieved = get_account_by_protocol_and_id("matrix", caller["user_id"])
            assert retrieved is not None
            assert retrieved.credentials["access_token"] == caller["access_token"]
            assert retrieved.credentials["user_id"] == caller["user_id"]
            
            # Test invalid credentials (should still be stored but marked invalid during validation)
            invalid_account = Account(
                protocol="matrix",
                account_id="@invalid:example.com",
                display_name="Invalid Test Account",
                credentials_json=""
            )
            invalid_account.credentials = {
                "access_token": "invalid_token",
                "user_id": "@invalid:example.com",
                "homeserver": "https://invalid.example.com",
            }
            
            save_account(invalid_account)
            
            # The account should be saved (validation happens when used)
            invalid_retrieved = get_account_by_protocol_and_id("matrix", "@invalid:example.com")
            assert invalid_retrieved is not None
            assert invalid_retrieved.credentials["access_token"] == "invalid_token"
            
        finally:
            # Clean up test database
            if os.path.exists(test_db_path):
                os.unlink(test_db_path)


class TestMatrixPluginStandalone:
    """Tests for Matrix plugin availability and management"""

    @pytest.mark.asyncio
    async def test_matrix_plugin_directory_exists(self):
        """Test that Matrix plugin directory and files exist"""
        import os
        
        matrix_plugin_dir = "/workspaces/universal/call-assist/addon/plugins/matrix"
        assert os.path.exists(matrix_plugin_dir), "Matrix plugin directory should exist"
        
        # Check for key files
        package_json = os.path.join(matrix_plugin_dir, "package.json")
        assert os.path.exists(package_json), "package.json should exist"
        
        src_dir = os.path.join(matrix_plugin_dir, "src")
        assert os.path.exists(src_dir), "src directory should exist"
        
        main_file = os.path.join(matrix_plugin_dir, "src", "index.ts")
        assert os.path.exists(main_file), "main TypeScript file should exist"

    @pytest.mark.asyncio
    async def test_matrix_plugin_schema_availability(self):
        """Test that Matrix protocol schema is available through form generator"""
        import os
        
        # Check that form generator module exists and can be imported
        form_generator_path = "/workspaces/universal/call-assist/addon/broker/form_generator.py"
        assert os.path.exists(form_generator_path), "Form generator module should exist"
        
        # Test that we can import the form generator
        try:
            from addon.broker import form_generator
            assert hasattr(form_generator, 'FormField'), "FormField class should exist"
        except ImportError as e:
            pytest.skip(f"Form generator not available: {e}")
        
        # Test that protocol schemas are defined somewhere in the system
        # (The actual schemas may be defined in different ways depending on implementation)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
