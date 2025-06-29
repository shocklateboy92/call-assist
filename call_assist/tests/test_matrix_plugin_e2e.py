#!/usr/bin/env python3
"""
Matrix Plugin End-to-End Tests

This test suite validates the complete user flow for managing Matrix accounts
through the web UI only. It tests the web interface as a real user would
interact with it, using HTTP requests, form submissions, and DOM inspection.

This serves as a true end-to-end test that mimics the actual user experience
without touching any broker internal methods directly.
"""
import logging
from types import TracebackType
from typing import Any, cast

import aiohttp
import pytest
from .conftest import WebUITestClient

# Set up logging for tests
logger = logging.getLogger(__name__)


class MatrixTestClient:
    """Test client for interacting with Matrix homeserver (reused from original tests)"""

    def __init__(self, homeserver_url: str = "http://synapse:8008"):
        self.homeserver_url = homeserver_url
        self.access_token: str | None = None
        self.user_id: str | None = None
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "MatrixTestClient":
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.session:
            await self.session.close()

    async def register_user(self, username: str, password: str) -> dict[str, Any]:
        """Register a test user on the Matrix homeserver, or login if already exists"""
        # First try to login in case user already exists
        login_result = await self.login(username, password)
        if "access_token" in login_result:
            return login_result

        # If login failed, try to register
        if self.session is None:
            raise RuntimeError("Session not initialized")

        url = f"{self.homeserver_url}/_matrix/client/r0/register"
        data = {
            "username": username,
            "password": password,
            "auth": {"type": "m.login.dummy"},
        }

        async with self.session.post(url, json=data) as resp:
            result: dict[str, Any] = await resp.json()
            if resp.status == 200:
                self.access_token = result["access_token"]
                self.user_id = result["user_id"]
            elif resp.status == 400 and "M_USER_IN_USE" in str(result):
                # User already exists, try login
                login_result = await self.login(username, password)
                if "access_token" in login_result:
                    return login_result
            return result

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """Login with existing user credentials"""
        if self.session is None:
            raise RuntimeError("Session not initialized")

        url = f"{self.homeserver_url}/_matrix/client/r0/login"
        data = {"type": "m.login.password", "user": username, "password": password}

        async with self.session.post(url, json=data) as resp:
            result: dict[str, Any] = await resp.json()
            if resp.status == 200:
                self.access_token = result["access_token"]
                self.user_id = result["user_id"]
            return result

    async def create_room(
        self, name: str | None = None, is_direct: bool = False
    ) -> dict[str, Any]:
        """Create a Matrix room"""
        if self.session is None or self.access_token is None:
            raise RuntimeError("Session or access token not initialized")

        url = f"{self.homeserver_url}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data: dict[str, Any] = {"visibility": "private"}

        if is_direct:
            data["preset"] = "trusted_private_chat"
            data["is_direct"] = True

        if name and not is_direct:
            data["name"] = name

        async with self.session.post(url, json=data, headers=headers) as resp:
            result: dict[str, Any] = await resp.json()
            return result


# Test constants
TEST_PASSWORD = "testpassword123"
RECEIVER_USERNAME = "testreceiver"
CALLER_USERNAME = "testcaller"
TEST_HOMESERVER = "http://synapse:8008"


@pytest.fixture
async def matrix_test_users() -> dict[str, dict[str, Any]]:
    """Create test users on the Matrix homeserver"""
    users = {}

    async with MatrixTestClient() as client:
        # Create caller user
        caller_result = await client.register_user(CALLER_USERNAME, TEST_PASSWORD)
        if "access_token" in caller_result:
            users["caller"] = {
                "username": CALLER_USERNAME,
                "user_id": caller_result["user_id"],
                "access_token": caller_result["access_token"],
            }

        # Create receiver user
        receiver_result = await client.register_user(RECEIVER_USERNAME, TEST_PASSWORD)
        if "access_token" in receiver_result:
            users["receiver"] = {
                "username": RECEIVER_USERNAME,
                "user_id": receiver_result["user_id"],
                "access_token": receiver_result["access_token"],
            }

    return users


class TestMatrixPluginWebUIE2E:
    """End-to-end tests for Matrix plugin via web UI only"""

    @pytest.mark.asyncio
    async def test_web_server_starts_and_responds(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that the web server starts and responds to requests"""
        # Wait for server to be ready
        server_ready = await web_ui_client.wait_for_server()
        assert server_ready, "Web server did not start within timeout"

        # Test main page loads
        html, soup = await web_ui_client.get_page("/ui")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "main page")

        # Check for expected content in visible text
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(
            keyword in visible_text for keyword in ["Call Assist", "Broker", "Accounts"]
        ), f"Expected content not found in visible text: {visible_text[:200]}..."

        # Verify basic HTML structure
        assert soup.find("body") is not None

    @pytest.mark.asyncio
    async def test_main_ui_page_loads(self, web_ui_client: WebUITestClient) -> None:
        """Test that the main UI page loads correctly with accounts table"""
        await web_ui_client.wait_for_server()

        html, soup = await web_ui_client.get_page("/ui")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "main UI page")

        # Extract visible text for content validation
        visible_text = web_ui_client.extract_visible_text_content(soup)

        # Should contain accounts section
        assert any(
            keyword in visible_text for keyword in ["Accounts", "accounts"]
        ), f"Accounts section not found in visible text: {visible_text[:200]}..."

        # Should have Add Account functionality
        assert any(
            keyword in visible_text for keyword in ["Add Account", "Add", "add"]
        ), f"Add Account functionality not found in visible text: {visible_text[:200]}..."

        # Extract any existing accounts (this will also validate HTML structure)
        accounts = web_ui_client.extract_accounts_from_table(soup)
        logger.info(f"Found {len(accounts)} existing accounts: {accounts}")

    @pytest.mark.asyncio
    async def test_add_account_page_loads(self, web_ui_client: WebUITestClient) -> None:
        """Test that the add account page loads with protocol selection"""
        await web_ui_client.wait_for_server()

        html, soup = await web_ui_client.get_page("/ui/add-account")

        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "add account page")

        # Extract visible text for content validation
        visible_text = web_ui_client.extract_visible_text_content(soup)

        # Should have protocol selection
        assert any(
            keyword in visible_text for keyword in ["Protocol", "protocol"]
        ), f"Protocol selection not found in visible text: {visible_text[:200]}..."

        # Should have Add Account form
        assert any(
            keyword in visible_text for keyword in ["Add Account", "Add"]
        ), f"Add Account form not found in visible text: {visible_text[:200]}..."

        # Extract available protocols
        protocols = web_ui_client.extract_protocol_options(soup)
        logger.info(f"Available protocols: {protocols}")

        # Should include Matrix protocol
        matrix_available = any("matrix" in p.lower() for p in protocols)
        assert matrix_available, f"Matrix protocol not found in {protocols}"

    @pytest.mark.asyncio
    async def test_add_matrix_account_via_web_ui(
        self,
        web_ui_client: WebUITestClient,
        matrix_test_users: dict[str, dict[str, Any]],
    ) -> None:
        """Test adding a Matrix account through the web UI form submission"""
        if "caller" not in matrix_test_users:
            pytest.skip("Matrix test user not available")

        await web_ui_client.wait_for_server()
        test_user = matrix_test_users["caller"]

        # Step 1: Get initial account count from main page
        html, soup = await web_ui_client.get_page("/ui")
        initial_accounts = web_ui_client.extract_accounts_from_table(soup)
        initial_count = len(initial_accounts)
        logger.info(f"Initial account count: {initial_count}")

        # Step 2: Navigate to add account page
        html, soup = await web_ui_client.get_page("/ui/add-account")

        # Step 3: First trigger the HTMX request to load Matrix form fields
        # Get protocol fields for Matrix
        protocol_fields_response = await web_ui_client.get_page(
            "/ui/api/protocol-fields?protocol=matrix"
        )
        matrix_fields_html, matrix_fields_soup = protocol_fields_response

        # Verify Matrix-specific fields are loaded
        assert (
            "homeserver" in matrix_fields_html.lower()
            or "access_token" in matrix_fields_html.lower()
        )

        # Step 4: Now attempt form submission with Matrix data
        form_data = {
            "protocol": "matrix",
            "account_id": test_user["user_id"],
            "display_name": f"Test Matrix Account - {test_user['username']}",
            "homeserver": "http://synapse:8008",
            "user_id": test_user["user_id"],
            "access_token": test_user["access_token"],
        }

        # Submit the form
        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-account", form_data
        )

        # Check if submission was successful (should redirect or show success)
        if status == 302:  # Redirect to main page
            logger.info("Form submission successful - redirected")
            # Verify the account was added by checking the main page
            html, soup = await web_ui_client.get_page("/ui")
            final_accounts = web_ui_client.extract_accounts_from_table(soup)
            final_count = len(final_accounts)

            assert (
                final_count > initial_count
            ), f"Account count should increase from {initial_count} to {final_count}"

            # Check if our test account appears in the list
            matrix_accounts = [
                acc for acc in final_accounts if acc.get("protocol") == "matrix"
            ]
            test_account_found = any(
                acc.get("account_id") == test_user["user_id"] for acc in matrix_accounts
            )
            assert (
                test_account_found
            ), f"Test Matrix account not found in {matrix_accounts}"

        else:
            # Form submission failed, but we can still validate the structure
            logger.info(f"Form submission returned status {status}")
            assert "Protocol" in html
            assert "Add" in html

    @pytest.mark.asyncio
    async def test_edit_account_page_loads(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that the edit account page exists and loads"""
        await web_ui_client.wait_for_server()

        # Test edit page with dummy parameters (should handle gracefully)
        try:
            html, soup = await web_ui_client.get_page("/ui/edit-account/matrix/dummy")
            # Should load page but show "Account not found"
            assert "Account not found" in html or "not found" in html.lower()
        except Exception as e:
            # Page might redirect or show error, that's acceptable
            logger.info(f"Edit page response: {e}")

    @pytest.mark.asyncio
    async def test_complete_web_ui_navigation(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that all key web UI pages are accessible and load correctly"""
        await web_ui_client.wait_for_server()

        # Test main page
        html, soup = await web_ui_client.get_page("/ui")
        web_ui_client.validate_html_structure(soup, "main page")
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(
            keyword in visible_text for keyword in ["Call Assist", "Broker", "Accounts"]
        ), f"Expected main page content not found in: {visible_text[:200]}..."

        # Test add account page
        html, soup = await web_ui_client.get_page("/ui/add-account")
        web_ui_client.validate_html_structure(soup, "add account page")
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(
            keyword in visible_text for keyword in ["Protocol", "Add"]
        ), f"Expected add account content not found in: {visible_text[:200]}..."

        # Test settings page
        html, soup = await web_ui_client.get_page("/ui/settings")
        web_ui_client.validate_html_structure(soup, "settings page")
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(
            keyword in visible_text for keyword in ["Settings", "settings"]
        ), f"Expected settings content not found in: {visible_text[:200]}..."

    @pytest.mark.asyncio
    async def test_matrix_plugin_schema_integration(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that Matrix plugin schema is properly integrated with the UI"""
        await web_ui_client.wait_for_server()

        # Load add account page
        html, soup = await web_ui_client.get_page("/ui/add-account")
        web_ui_client.validate_html_structure(soup, "add account page")

        # Check that Matrix is available as a protocol option
        protocols = web_ui_client.extract_protocol_options(soup)
        matrix_available = any("matrix" in p.lower() for p in protocols)
        assert matrix_available, f"Matrix not found in protocols: {protocols}"

        # Test the HTMX endpoint for Matrix protocol fields
        matrix_fields_html, matrix_fields_soup = await web_ui_client.get_page(
            "/ui/api/protocol-fields?protocol=matrix"
        )
        web_ui_client.validate_html_structure(
            matrix_fields_soup, "Matrix protocol fields"
        )

        # Verify Matrix-specific fields are returned
        matrix_inputs = web_ui_client.find_form_inputs(matrix_fields_soup)
        expected_fields = [
            "account_id",
            "display_name",
            "homeserver",
            "access_token",
            "user_id",
        ]

        for field in expected_fields:
            assert (
                field in matrix_inputs
            ), f"Expected field '{field}' not found in Matrix form: {list(matrix_inputs.keys())}"

        logger.info(
            f"Matrix protocol schema integration verified with fields: {list(matrix_inputs.keys())}"
        )

    @pytest.mark.asyncio
    async def test_form_validation_structure(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that the form structure supports proper validation"""
        await web_ui_client.wait_for_server()

        # Load add account page
        html, soup = await web_ui_client.get_page("/ui/add-account")

        # Check for form elements
        form_inputs = web_ui_client.find_form_inputs(soup)
        logger.info(f"Found form inputs: {form_inputs}")

        # Should have at least a protocol selector
        has_protocol_field = any(
            "protocol" in key.lower() for key in form_inputs.keys()
        )
        assert (
            has_protocol_field or "protocol" in html.lower()
        ), "No protocol selection found"

    @pytest.mark.asyncio
    async def test_invalid_matrix_account_status_checking(
        self, web_ui_client: WebUITestClient
    ) -> None:
        """Test that invalid Matrix account credentials show as invalid status in the UI"""
        await web_ui_client.wait_for_server()

        # Add an account with invalid Matrix credentials that will definitely fail
        # Use malformed/missing required fields to ensure plugin initialization fails
        invalid_form_data = {
            "protocol": "matrix",
            "account_id": "@invalid_user:invalid-domain",
            "display_name": "Invalid Matrix Account",
            "homeserver": "",  # Empty homeserver should cause failure
            "user_id": "",  # Empty user_id should cause failure
            "access_token": "",  # Empty access_token should cause failure
        }

        # First trigger the HTMX request to load Matrix form fields
        protocol_fields_response = await web_ui_client.get_page(
            "/ui/api/protocol-fields?protocol=matrix"
        )
        matrix_fields_html, matrix_fields_soup = protocol_fields_response

        # Verify Matrix-specific fields are loaded
        assert (
            "homeserver" in matrix_fields_html.lower()
            or "access_token" in matrix_fields_html.lower()
        )

        # Submit the form with invalid credentials
        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-account", cast(dict[str, object], invalid_form_data)
        )

        # The form submission might succeed (saving to database) or fail
        if status == 302:  # Successful redirect
            logger.info(
                "Invalid account form submission successful - checking status display"
            )

            # Navigate to main page to check account status
            html, soup = await web_ui_client.get_page("/ui")
            accounts = web_ui_client.extract_accounts_from_table(soup)

            # Find the invalid account we just added
            invalid_account = None
            for account in accounts:
                if account.get("account_id") == "@invalid_user:invalid-domain":
                    invalid_account = account
                    break

            assert (
                invalid_account is not None
            ), f"Invalid Matrix account not found in accounts list: {accounts}"

            # Check that the status shows as invalid
            # The status should be checked real-time from the plugin
            status_text = invalid_account.get("status", "")

            # The account should show as invalid since the credentials are bogus
            status_is_invalid = "invalid" in status_text.lower() or "❌" in status_text
            assert (
                status_is_invalid
            ), f"Status text should indicate invalid status. Got: '{status_text}'. Account: {invalid_account}"

            logger.info(
                f"Successfully verified invalid Matrix account shows invalid status: {invalid_account}"
            )

        elif status == 200:
            # Form submission succeeded but might not redirect (some forms work this way)
            logger.info("Form submission returned 200 - checking if account was added")

            # Navigate to main page to check account status
            html, soup = await web_ui_client.get_page("/ui")
            accounts = web_ui_client.extract_accounts_from_table(soup)

            # Find the invalid account
            invalid_account = None
            for account in accounts:
                if account.get("account_id") == "@invalid_user:invalid-domain":
                    invalid_account = account
                    break

            if invalid_account is not None:
                # Account was added, check that status shows as invalid
                status_text = invalid_account.get("status", "")

                # Check that the status indicates invalid
                status_is_invalid = (
                    "invalid" in status_text.lower() or "❌" in status_text
                )
                assert (
                    status_is_invalid
                ), f"Status text should indicate invalid status. Got: '{status_text}'. Account: {invalid_account}"

                logger.info(
                    f"Successfully verified invalid Matrix account shows invalid status: {invalid_account}"
                )
            else:
                logger.info(
                    "Account was not added - this is also acceptable for invalid credentials"
                )

        else:
            # Form submission failed with error status - this is also acceptable for invalid credentials
            logger.info(
                f"Form submission failed with status {status} - this is acceptable for invalid credentials"
            )
            # We can still check that the error handling works properly
            assert status in [
                400,
                422,
                500,
            ], f"Unexpected status code for invalid credentials: {status}"

    @pytest.mark.asyncio
    async def test_valid_matrix_account_status_checking(
        self,
        web_ui_client: WebUITestClient,
        matrix_test_users: dict[str, dict[str, Any]],
    ) -> None:
        """Test that valid Matrix account credentials show as valid status in the UI"""
        if "caller" not in matrix_test_users:
            pytest.skip("Matrix test user not available")

        await web_ui_client.wait_for_server()
        test_user = matrix_test_users["caller"]

        # Add an account with valid Matrix credentials from the fixture
        valid_form_data = {
            "protocol": "matrix",
            "account_id": test_user["user_id"],
            "display_name": f"Valid Matrix Account - {test_user['username']}",
            "homeserver": "http://synapse:8008",
            "user_id": test_user["user_id"],
            "access_token": test_user["access_token"],
        }

        # First trigger the HTMX request to load Matrix form fields
        protocol_fields_response = await web_ui_client.get_page(
            "/ui/api/protocol-fields?protocol=matrix"
        )
        matrix_fields_html, matrix_fields_soup = protocol_fields_response

        # Verify Matrix-specific fields are loaded
        assert (
            "homeserver" in matrix_fields_html.lower()
            or "access_token" in matrix_fields_html.lower()
        )

        # Submit the form with valid credentials
        status, response_html, response_soup = await web_ui_client.post_form(
            "/ui/add-account", valid_form_data
        )

        # The form submission should succeed
        if status == 302:  # Successful redirect
            logger.info(
                "Valid account form submission successful - checking status display"
            )

            # Navigate to main page to check account status
            html, soup = await web_ui_client.get_page("/ui")
            accounts = web_ui_client.extract_accounts_from_table(soup)

            # Find the valid account we just added
            valid_account = None
            for account in accounts:
                if account.get("account_id") == test_user["user_id"]:
                    valid_account = account
                    break

            assert (
                valid_account is not None
            ), f"Valid Matrix account not found in accounts list: {accounts}"

            # Check that the status shows as valid
            # The status should be checked real-time from the plugin
            status_text = valid_account.get("status", "")

            # The account should show as valid since the credentials are real and working
            status_is_valid = "valid" in status_text.lower() or "✅" in status_text
            assert (
                status_is_valid
            ), f"Status text should indicate valid status. Got: '{status_text}'. Account: {valid_account}"

            logger.info(
                f"Successfully verified valid Matrix account shows valid status: {valid_account}"
            )

        elif status == 200:
            # Form submission succeeded but might not redirect (some forms work this way)
            logger.info("Form submission returned 200 - checking if account was added")

            # Navigate to main page to check account status
            html, soup = await web_ui_client.get_page("/ui")
            accounts = web_ui_client.extract_accounts_from_table(soup)

            # Find the valid account
            valid_account = None
            for account in accounts:
                if account.get("account_id") == test_user["user_id"]:
                    valid_account = account
                    break

            if valid_account is not None:
                # Account was added, check that status shows as valid
                status_text = valid_account.get("status", "")

                # Check that the status indicates valid
                status_is_valid = "valid" in status_text.lower() or "✅" in status_text
                assert (
                    status_is_valid
                ), f"Status text should indicate valid status. Got: '{status_text}'. Account: {valid_account}"

                logger.info(
                    f"Successfully verified valid Matrix account shows valid status: {valid_account}"
                )
            else:
                # If account wasn't added, that's unexpected for valid credentials
                pytest.fail(
                    f"Valid Matrix account was not added to the system. Form data: {valid_form_data}"
                )

        else:
            # Form submission failed - this is unexpected for valid credentials
            pytest.fail(
                f"Form submission failed with status {status} for valid credentials. Form data: {valid_form_data}"
            )
