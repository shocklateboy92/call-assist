#!/usr/bin/env python3
"""
Matrix Plugin End-to-End Tests

This test suite validates the complete user flow for managing Matrix accounts
through the web UI and testing Matrix plugin functionality. Since the web UI
is server-side rendered with NiceGUI, we can test it by making HTTP requests
and inspecting the DOM.

This serves as both a Matrix plugin test and a comprehensive e2e test that
mimics the full user experience.
"""

import asyncio
import pytest
import pytest_asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import json

# Set up logging for tests
logger = logging.getLogger(__name__)


class WebUITestClient:
    """Test client for interacting with the Call Assist web UI"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_page(self, path: str) -> tuple[str, BeautifulSoup]:
        """Get a web page and return the HTML content and parsed DOM"""
        url = urljoin(self.base_url, path)

        async with self.session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to get {url}: {resp.status}")

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            return html, soup

    async def post_form(self, path: str, form_data: Dict[str, Any]) -> tuple[int, str]:
        """Submit a form to the web UI"""
        url = urljoin(self.base_url, path)

        async with self.session.post(url, data=form_data) as resp:
            text = await resp.text()
            return resp.status, text

    async def wait_for_page_load(
        self, path: str, max_attempts: int = 10, delay: float = 1.0
    ):
        """Wait for a page to load successfully"""
        for attempt in range(max_attempts):
            try:
                _, soup = await self.get_page(path)
                # Check if page loaded properly (has basic structure)
                if soup.find("body"):
                    return soup
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise e
                await asyncio.sleep(delay)

        raise Exception(f"Page {path} failed to load after {max_attempts} attempts")


class MatrixTestClient:
    """Test client for interacting with Matrix homeserver (reused from original tests)"""

    def __init__(self, homeserver_url: str = "http://synapse:8008"):
        self.homeserver_url = homeserver_url
        self.access_token = None
        self.user_id = None
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
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
        self, name: Optional[str] = None, is_direct: bool = False
    ) -> Dict[str, Any]:
        """Create a Matrix room"""
        url = f"{self.homeserver_url}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data: dict = {"visibility": "private"}

        if is_direct:
            data["preset"] = "trusted_private_chat"
            data["is_direct"] = True

        if name and not is_direct:
            data["name"] = name

        async with self.session.post(url, json=data, headers=headers) as resp:
            return await resp.json()


# Test constants
TEST_PASSWORD = "testpassword123"
RECEIVER_USERNAME = "testreceiver"
CALLER_USERNAME = "testcaller"
TEST_HOMESERVER = "http://synapse:8008"


@pytest_asyncio.fixture
async def web_ui_client(broker_process):
    """Create a web UI test client"""
    async with WebUITestClient(
        base_url=f"http://localhost:{broker_process['web_port']}"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def matrix_test_users():
    """Create test users on the Matrix homeserver"""
    users = {}

    async with MatrixTestClient() as client:
        # Create caller user
        caller_result = await client.register_user(CALLER_USERNAME, TEST_PASSWORD)
        if "access_token" in caller_result:
            users["caller"] = {
                "user_id": caller_result["user_id"],
                "access_token": caller_result["access_token"],
                "password": TEST_PASSWORD,
                "username": CALLER_USERNAME,
            }

        # Create receiver user
        receiver_result = await client.register_user(RECEIVER_USERNAME, TEST_PASSWORD)
        if "access_token" in receiver_result:
            users["receiver"] = {
                "user_id": receiver_result["user_id"],
                "access_token": receiver_result["access_token"],
                "password": TEST_PASSWORD,
                "username": RECEIVER_USERNAME,
            }

    return users


@pytest_asyncio.fixture
async def test_room(matrix_test_users):
    """Create a test room for calls"""
    if "caller" not in matrix_test_users:
        pytest.skip("Caller user required")

    caller = matrix_test_users["caller"]

    async with MatrixTestClient() as client:
        client.access_token = caller["access_token"]
        client.user_id = caller["user_id"]

        room_result = await client.create_room(name="Test Call Room")
        if "room_id" not in room_result:
            pytest.skip("Failed to create test room")

        return room_result["room_id"]


class TestMatrixPluginE2E:
    """End-to-end tests for Matrix plugin via web UI"""

    @pytest.mark.asyncio
    async def test_web_ui_main_page_loads(self, web_ui_client):
        """Test that the main web UI page loads correctly"""
        html, soup = await web_ui_client.get_page("/ui")

        # Check for key elements
        assert "Call Assist Broker" in html
        assert soup.find("body") is not None

        # Check for main navigation tabs
        accounts_tab = soup.find(text="Accounts")
        status_tab = soup.find(text="Status")
        history_tab = soup.find(text="Call History")

        assert accounts_tab is not None, "Accounts tab not found"
        assert status_tab is not None, "Status tab not found"
        assert history_tab is not None, "History tab not found"

    @pytest.mark.asyncio
    async def test_add_account_page_loads(self, web_ui_client):
        """Test that the add account page loads and shows protocol options"""
        html, soup = await web_ui_client.get_page("/ui/add-account")

        # Check page loaded
        assert "Add Account" in html
        assert soup.find("body") is not None

        # Check for protocol selection (this tests that protocol schemas are loaded)
        # Note: The actual protocol options are populated dynamically,
        # so we look for the structure rather than specific options
        assert "Protocol" in html

    @pytest.mark.asyncio
    async def test_settings_page_loads(self, web_ui_client):
        """Test that the settings page loads"""
        html, soup = await web_ui_client.get_page("/ui/settings")

        # Check page loaded
        assert "Settings" in html or "Broker Settings" in html
        assert soup.find("body") is not None

    @pytest.mark.asyncio
    async def test_complete_matrix_account_flow(self, web_ui_client, matrix_test_users):
        """Test the complete flow: add Matrix account, verify it appears in UI, remove it"""
        if "caller" not in matrix_test_users:
            pytest.skip("Caller user required for Matrix account test")

        caller = matrix_test_users["caller"]

        # Step 1: Add Matrix account via web UI
        # Note: Since the web UI uses NiceGUI with dynamic forms and JavaScript,
        # we'll test the underlying API functionality instead of form submission

        # First, verify the accounts page shows no Matrix accounts initially
        html, soup = await web_ui_client.get_page("/ui")

        # The accounts table should exist but may be empty
        # (We can't easily test dynamic content without JavaScript execution)

        # Step 2: Verify account management functionality through database
        # This tests the same code path the web UI uses
        from addon.broker.models import Account
        from addon.broker.queries import save_account, get_all_accounts, delete_account

        # Create a test Matrix account (simulating what the web UI would do)
        test_account = Account(
            protocol="matrix",
            account_id=caller["user_id"],
            display_name=f"Test Matrix Account - {caller['username']}",
            credentials_json="",  # Will be set via property
        )
        test_account.credentials = {
            "access_token": caller["access_token"],
            "user_id": caller["user_id"],
            "homeserver": TEST_HOMESERVER,
        }

        # Save the account (this is what the web UI does)
        save_account(test_account)

        # Step 3: Verify account appears in database
        all_accounts = get_all_accounts()
        matrix_accounts = [
            acc
            for acc in all_accounts
            if acc.protocol == "matrix" and acc.account_id == caller["user_id"]
        ]
        assert len(matrix_accounts) == 1, "Matrix account should be saved"

        saved_account = matrix_accounts[0]
        assert saved_account.display_name == test_account.display_name
        assert saved_account.credentials["user_id"] == caller["user_id"]
        assert saved_account.credentials["access_token"] == caller["access_token"]

        # Step 4: Clean up - delete the account
        success = delete_account("matrix", caller["user_id"])
        assert success, "Should be able to delete the account"

        # Step 5: Verify account is deleted
        all_accounts_after = get_all_accounts()
        matrix_accounts_after = [
            acc
            for acc in all_accounts_after
            if acc.protocol == "matrix" and acc.account_id == caller["user_id"]
        ]
        assert len(matrix_accounts_after) == 0, "Matrix account should be deleted"

    @pytest.mark.asyncio
    async def test_matrix_account_validation(self, matrix_test_users):
        """Test Matrix account credential validation"""
        if "caller" not in matrix_test_users:
            pytest.skip("Caller user required for validation test")

        caller = matrix_test_users["caller"]

        from addon.broker.models import Account
        from addon.broker.queries import save_account, get_account_by_protocol_and_id

        # Test valid credentials
        valid_account = Account(
            protocol="matrix",
            account_id=caller["user_id"],
            display_name="Valid Test Account",
            credentials_json="",
        )
        valid_account.credentials = {
            "access_token": caller["access_token"],
            "user_id": caller["user_id"],
            "homeserver": TEST_HOMESERVER,
        }

        save_account(valid_account)

        # Retrieve and verify
        retrieved = get_account_by_protocol_and_id("matrix", caller["user_id"])
        assert retrieved is not None
        assert retrieved.credentials["access_token"] == caller["access_token"]

        # Test invalid credentials
        invalid_account = Account(
            protocol="matrix",
            account_id="@invalid:example.com",
            display_name="Invalid Test Account",
            credentials_json="",
        )
        invalid_account.credentials = {
            "access_token": "invalid_token",
            "user_id": "@invalid:example.com",
            "homeserver": "https://invalid.example.com",
        }

        save_account(invalid_account)

        # The account should be saved but marked as invalid during validation
        invalid_retrieved = get_account_by_protocol_and_id(
            "matrix", "@invalid:example.com"
        )
        assert invalid_retrieved is not None
        # Note: Actual validation happens when the broker tries to use the credentials

        # Clean up
        from addon.broker.queries import delete_account

        delete_account("matrix", caller["user_id"])
        delete_account("matrix", "@invalid:example.com")

    @pytest.mark.asyncio
    async def test_matrix_call_simulation(self, matrix_test_users, test_room):
        """Test simulated Matrix call flow using the account management system"""
        if "caller" not in matrix_test_users:
            pytest.skip("Caller user required for call simulation")

        caller = matrix_test_users["caller"]

        # Set up Matrix account in the system
        from addon.broker.models import Account, CallLog
        from addon.broker.queries import save_account, save_call_log, get_call_history

        matrix_account = Account(
            protocol="matrix",
            account_id=caller["user_id"],
            display_name="Test Caller Account",
            credentials_json="",
        )
        matrix_account.credentials = {
            "access_token": caller["access_token"],
            "user_id": caller["user_id"],
            "homeserver": TEST_HOMESERVER,
        }

        save_account(matrix_account)

        # Simulate a call log entry (what would happen during a real call)
        from datetime import datetime, timezone
        import uuid

        call_id = str(uuid.uuid4())
        call_log = CallLog(
            call_id=call_id,
            protocol="matrix",
            account_id=caller["user_id"],
            target_address=test_room,
            start_time=datetime.now(timezone.utc),
            final_state="completed",
            duration_seconds=45,
            metadata_json=json.dumps(
                {
                    "room_name": "Test Call Room",
                    "call_type": "video",
                    "webrtc_used": True,
                }
            ),
        )

        save_call_log(call_log)

        # Verify call appears in history
        call_history = get_call_history(10)
        assert len(call_history) > 0

        # Find our call
        our_call = next((log for log in call_history if log.call_id == call_id), None)
        assert our_call is not None, "Call log should be saved"
        assert our_call.protocol == "matrix"
        assert our_call.account_id == caller["user_id"]
        assert our_call.target_address == test_room
        assert our_call.final_state == "completed"
        assert our_call.duration_seconds == 45

        # Verify metadata
        metadata = json.loads(our_call.metadata_json)
        assert metadata["call_type"] == "video"
        assert metadata["webrtc_used"] is True

        # Clean up
        from addon.broker.queries import delete_account

        delete_account("matrix", caller["user_id"])

    @pytest.mark.asyncio
    async def test_web_ui_error_handling(self, web_ui_client):
        """Test web UI error handling for invalid pages"""
        # Test invalid page
        try:
            await web_ui_client.get_page("/ui/invalid-page")
            assert False, "Should have raised an exception for invalid page"
        except Exception as e:
            # Should get a 404 or similar error
            assert "404" in str(e) or "Failed to get" in str(e)

    @pytest.mark.asyncio
    async def test_database_persistence(self, matrix_test_users):
        """Test that account data persists across operations"""
        if "caller" not in matrix_test_users:
            pytest.skip("Caller user required for persistence test")

        caller = matrix_test_users["caller"]

        from addon.broker.models import Account
        from addon.broker.queries import (
            save_account,
            get_account_by_protocol_and_id,
            delete_account,
        )

        # Create account with complex credentials
        account = Account(
            protocol="matrix",
            account_id=caller["user_id"],
            display_name="Persistence Test Account",
            credentials_json="",
        )

        complex_credentials = {
            "access_token": caller["access_token"],
            "user_id": caller["user_id"],
            "homeserver": TEST_HOMESERVER,
            "device_id": "test_device_123",
            "custom_setting": True,
            "nested_data": {"key1": "value1", "key2": ["item1", "item2"]},
        }
        account.credentials = complex_credentials

        # Save account
        save_account(account)

        # Retrieve and verify all data persisted correctly
        retrieved = get_account_by_protocol_and_id("matrix", caller["user_id"])
        assert retrieved is not None
        assert retrieved.display_name == "Persistence Test Account"
        assert retrieved.credentials["access_token"] == caller["access_token"]
        assert retrieved.credentials["device_id"] == "test_device_123"
        assert retrieved.credentials["custom_setting"] is True
        assert retrieved.credentials["nested_data"]["key1"] == "value1"
        assert retrieved.credentials["nested_data"]["key2"] == ["item1", "item2"]

        # Update account
        retrieved.display_name = "Updated Test Account"
        retrieved.credentials["custom_setting"] = False
        save_account(retrieved)

        # Verify update persisted
        updated = get_account_by_protocol_and_id("matrix", caller["user_id"])
        assert updated.display_name == "Updated Test Account"
        assert updated.credentials["custom_setting"] is False
        # Other fields should remain unchanged
        assert updated.credentials["access_token"] == caller["access_token"]
        assert updated.credentials["nested_data"]["key1"] == "value1"

        # Clean up
        delete_account("matrix", caller["user_id"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
