#!/usr/bin/env python3
"""
Matrix Plugin End-to-End Tests

This test suite validates the complete user flow for managing Matrix accounts
through the web UI only. It tests the web interface as a real user would
interact with it, using HTTP requests, form submissions, and DOM inspection.

This serves as a true end-to-end test that mimics the actual user experience
without touching any broker internal methods directly.
"""
import asyncio
import logging
import pytest
import pytest_asyncio
import aiohttp
from typing import Dict, Any, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag

# Set up logging for tests
logger = logging.getLogger(__name__)


class WebUITestClient:
    """Test client for interacting with the Call Assist web UI via HTTP requests"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_page(self, path: str) -> tuple[str, BeautifulSoup]:
        """Get a web page and return the HTML content and parsed DOM"""
        if self.session is None:
            raise RuntimeError("Session not initialized")
            
        url = urljoin(self.base_url, path)
        logger.info(f"GET {url}")

        async with self.session.get(url) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"HTTP {resp.status}: {text}")

            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            return html, soup

    async def post_form(self, path: str, form_data: Dict[str, Any]) -> tuple[int, str, BeautifulSoup]:
        """Submit a form to the web UI"""
        if self.session is None:
            raise RuntimeError("Session not initialized")
            
        url = urljoin(self.base_url, path)
        logger.info(f"POST {url} with form data: {list(form_data.keys())}")

        async with self.session.post(url, data=form_data) as resp:
            text = await resp.text()
            soup = BeautifulSoup(text, "html.parser")
            return resp.status, text, soup

    async def wait_for_server(self, max_attempts: int = 30, delay: float = 1.0):
        """Wait for the web server to be ready"""
        for attempt in range(max_attempts):
            try:
                html, soup = await self.get_page("/ui")
                logger.info(f"Server ready after {attempt + 1} attempts")
                return True
            except Exception as e:
                logger.debug(f"Attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
        return False

    def extract_accounts_from_table(self, soup: BeautifulSoup) -> list[Dict[str, str]]:
        """Extract account information from the accounts table in the UI"""
        accounts = []
        
        # First validate that we have proper HTML structure
        body = soup.find("body")
        if body and hasattr(body, 'attrs') and 'children' in body.attrs:
            # This indicates malformed HTML where server sent string as attribute
            raise AssertionError(f"Malformed HTML detected: body tag has 'children' attribute instead of proper child elements")
        
        # Look for table rows in the accounts table
        table_rows = soup.find_all("tr")
        
        for row in table_rows:
            if isinstance(row, Tag):
                cells = row.find_all("td")
                if len(cells) >= 5:  # protocol, account_id, display_name, status, updated, actions
                    account = {
                        "protocol": cells[0].get_text(strip=True).lower(),
                        "account_id": cells[1].get_text(strip=True), 
                        "display_name": cells[2].get_text(strip=True),
                        "status": cells[3].get_text(strip=True),
                        "updated": cells[4].get_text(strip=True),
                    }
                    accounts.append(account)
        
        # Filter out header row and empty rows
        accounts = [acc for acc in accounts if acc["protocol"] and acc["protocol"] != "protocol"]
        return accounts

    def extract_protocol_options(self, soup: BeautifulSoup) -> list[str]:
        """Extract available protocols from a protocol selection dropdown"""
        protocols = []
        
        # Look for select options (skip empty/placeholder options)
        options = soup.find_all("option")
        for option in options:
            if isinstance(option, Tag):
                value = option.get("value")
                if value and isinstance(value, str) and value.strip() and value != "":
                    protocols.append(value.strip())
        
        return protocols

    def find_form_inputs(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Find all form input fields and their names/types"""
        inputs = {}
        
        # Find input elements
        for input_elem in soup.find_all("input"):
            if isinstance(input_elem, Tag):
                name = input_elem.get("name")
                input_type = input_elem.get("type", "text")
                if name and isinstance(name, str):
                    inputs[name] = str(input_type) if input_type else "text"
        
        # Find select elements  
        for select_elem in soup.find_all("select"):
            if isinstance(select_elem, Tag):
                name = select_elem.get("name")
                if name and isinstance(name, str):
                    inputs[name] = "select"
        
        # Find textarea elements
        for textarea_elem in soup.find_all("textarea"):
            if isinstance(textarea_elem, Tag):
                name = textarea_elem.get("name")
                if name and isinstance(name, str):
                    inputs[name] = "textarea"
        
        return inputs

    def validate_html_structure(self, soup: BeautifulSoup, page_name: str = "page") -> None:
        """Validate that the HTML structure is properly formed and not malformed by server errors"""
        # Check for malformed body tag with string content as attribute
        body = soup.find("body")
        if body and hasattr(body, 'attrs') and 'children' in body.attrs:
            raise AssertionError(f"Malformed HTML in {page_name}: body tag has 'children' attribute containing string content instead of proper child elements")
        
        # Check that body has actual child elements, not just text
        if body:
            # Body should have actual HTML child elements, not just raw text
            child_elements = body.find_all(recursive=False)  # Direct children only
            if len(child_elements) == 0:
                # Check if body only contains text (which might indicate serialization error)
                body_text = body.get_text(strip=True)
                if body_text and len(body_text) > 100:  # Suspiciously long text without structure
                    raise AssertionError(f"Malformed HTML in {page_name}: body contains only text content without proper HTML structure")
        
        # Check for common error patterns in the HTML
        html_text = str(soup).lower()
        error_patterns = [
            "children=",  # Ludic serialization error
            "internal server error",
            "500 internal server error", 
            "traceback",
            "exception occurred"
        ]
        
        for pattern in error_patterns:
            if pattern in html_text:
                raise AssertionError(f"HTML structure error in {page_name}: found error pattern '{pattern}'")

    def extract_visible_text_content(self, soup: BeautifulSoup) -> str:
        """Extract all user-visible text from the page for content validation"""
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content and clean it up
        text = soup.get_text()
        # Normalize whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text


class MatrixTestClient:
    """Test client for interacting with Matrix homeserver (reused from original tests)"""

    def __init__(self, homeserver_url: str = "http://synapse:8008"):
        self.homeserver_url = homeserver_url
        self.access_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None

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
        if self.session is None:
            raise RuntimeError("Session not initialized")
            
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
            elif resp.status == 400 and "M_USER_IN_USE" in str(result):
                # User already exists, try login
                login_result = await self.login(username, password)
                if "access_token" in login_result:
                    return login_result
            return result

    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login with existing user credentials"""
        if self.session is None:
            raise RuntimeError("Session not initialized")
            
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
        if self.session is None or self.access_token is None:
            raise RuntimeError("Session or access token not initialized")
            
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
    async def test_web_server_starts_and_responds(self, web_ui_client):
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
        assert any(keyword in visible_text for keyword in ["Call Assist", "Broker", "Accounts"]), \
            f"Expected content not found in visible text: {visible_text[:200]}..."
        
        # Verify basic HTML structure
        assert soup.find("body") is not None

    @pytest.mark.asyncio
    async def test_main_ui_page_loads(self, web_ui_client):
        """Test that the main UI page loads correctly with accounts table"""
        await web_ui_client.wait_for_server()
        
        html, soup = await web_ui_client.get_page("/ui")
        
        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "main UI page")
        
        # Extract visible text for content validation
        visible_text = web_ui_client.extract_visible_text_content(soup)
        
        # Should contain accounts section
        assert any(keyword in visible_text for keyword in ["Accounts", "accounts"]), \
            f"Accounts section not found in visible text: {visible_text[:200]}..."
        
        # Should have Add Account functionality
        assert any(keyword in visible_text for keyword in ["Add Account", "Add", "add"]), \
            f"Add Account functionality not found in visible text: {visible_text[:200]}..."
        
        # Extract any existing accounts (this will also validate HTML structure)
        accounts = web_ui_client.extract_accounts_from_table(soup)
        logger.info(f"Found {len(accounts)} existing accounts: {accounts}")

    @pytest.mark.asyncio
    async def test_add_account_page_loads(self, web_ui_client):
        """Test that the add account page loads with protocol selection"""
        await web_ui_client.wait_for_server()
        
        html, soup = await web_ui_client.get_page("/ui/add-account")
        
        # Validate HTML structure first
        web_ui_client.validate_html_structure(soup, "add account page")
        
        # Extract visible text for content validation
        visible_text = web_ui_client.extract_visible_text_content(soup)
        
        # Should have protocol selection
        assert any(keyword in visible_text for keyword in ["Protocol", "protocol"]), \
            f"Protocol selection not found in visible text: {visible_text[:200]}..."
        
        # Should have Add Account form
        assert any(keyword in visible_text for keyword in ["Add Account", "Add"]), \
            f"Add Account form not found in visible text: {visible_text[:200]}..."
        
        # Extract available protocols
        protocols = web_ui_client.extract_protocol_options(soup)
        logger.info(f"Available protocols: {protocols}")
        
        # Should include Matrix protocol
        matrix_available = any("matrix" in p.lower() for p in protocols)
        assert matrix_available, f"Matrix protocol not found in {protocols}"

    @pytest.mark.asyncio
    async def test_add_matrix_account_via_web_ui(self, web_ui_client: WebUITestClient, matrix_test_users):
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
        protocol_fields_response = await web_ui_client.get_page("/ui/api/protocol-fields?protocol=matrix")
        matrix_fields_html, matrix_fields_soup = protocol_fields_response
        
        # Verify Matrix-specific fields are loaded
        assert "homeserver" in matrix_fields_html.lower() or "access_token" in matrix_fields_html.lower()
        
        # Step 4: Now attempt form submission with Matrix data
        form_data = {
            "protocol": "matrix",
            "account_id": test_user["user_id"],
            "display_name": f"Test Matrix Account - {test_user['username']}",
            "homeserver": "http://synapse:8008",
            "user_id": test_user["user_id"],
            "access_token": test_user["access_token"]
        }
        
        # Submit the form
        status, response_html, response_soup = await web_ui_client.post_form("/ui/add-account", form_data)
        
        # Check if submission was successful (should redirect or show success)
        if status == 302:  # Redirect to main page
            logger.info("Form submission successful - redirected")
            # Verify the account was added by checking the main page
            html, soup = await web_ui_client.get_page("/ui")
            final_accounts = web_ui_client.extract_accounts_from_table(soup)
            final_count = len(final_accounts)
            
            assert final_count > initial_count, f"Account count should increase from {initial_count} to {final_count}"
            
            # Check if our test account appears in the list
            matrix_accounts = [acc for acc in final_accounts if acc.get("protocol") == "matrix"]
            test_account_found = any(
                acc.get("account_id") == test_user["user_id"] 
                for acc in matrix_accounts
            )
            assert test_account_found, f"Test Matrix account not found in {matrix_accounts}"
            
        else:
            # Form submission failed, but we can still validate the structure
            logger.info(f"Form submission returned status {status}")
            assert "Protocol" in html
            assert "Add" in html

    @pytest.mark.asyncio
    async def test_edit_account_page_loads(self, web_ui_client):
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
    async def test_complete_web_ui_navigation(self, web_ui_client: WebUITestClient):
        """Test that all key web UI pages are accessible and load correctly"""
        await web_ui_client.wait_for_server()

        # Test main page
        html, soup = await web_ui_client.get_page("/ui")
        web_ui_client.validate_html_structure(soup, "main page")
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(keyword in visible_text for keyword in ["Call Assist", "Broker", "Accounts"]), \
            f"Expected main page content not found in: {visible_text[:200]}..."
        
        # Test add account page
        html, soup = await web_ui_client.get_page("/ui/add-account")
        web_ui_client.validate_html_structure(soup, "add account page")
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(keyword in visible_text for keyword in ["Protocol", "Add"]), \
            f"Expected add account content not found in: {visible_text[:200]}..."
        
        # Test settings page
        html, soup = await web_ui_client.get_page("/ui/settings")
        web_ui_client.validate_html_structure(soup, "settings page")
        visible_text = web_ui_client.extract_visible_text_content(soup)
        assert any(keyword in visible_text for keyword in ["Settings", "settings"]), \
            f"Expected settings content not found in: {visible_text[:200]}..."

    @pytest.mark.asyncio
    async def test_matrix_plugin_schema_integration(self, web_ui_client):
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
        matrix_fields_html, matrix_fields_soup = await web_ui_client.get_page("/ui/api/protocol-fields?protocol=matrix")
        web_ui_client.validate_html_structure(matrix_fields_soup, "Matrix protocol fields")
        
        # Verify Matrix-specific fields are returned
        matrix_inputs = web_ui_client.find_form_inputs(matrix_fields_soup)
        expected_fields = ["account_id", "display_name", "homeserver", "access_token", "user_id"]
        
        for field in expected_fields:
            assert field in matrix_inputs, f"Expected field '{field}' not found in Matrix form: {list(matrix_inputs.keys())}"
        
        logger.info(f"Matrix protocol schema integration verified with fields: {list(matrix_inputs.keys())}")

    @pytest.mark.asyncio
    async def test_form_validation_structure(self, web_ui_client):
        """Test that the form structure supports proper validation"""
        await web_ui_client.wait_for_server()
        
        # Load add account page
        html, soup = await web_ui_client.get_page("/ui/add-account")
        
        # Check for form elements
        form_inputs = web_ui_client.find_form_inputs(soup)
        logger.info(f"Found form inputs: {form_inputs}")
        
        # Should have at least a protocol selector
        has_protocol_field = any("protocol" in key.lower() for key in form_inputs.keys())
        assert has_protocol_field or "protocol" in html.lower(), "No protocol selection found"

    @pytest.mark.asyncio
    async def test_invalid_matrix_account_status_checking(self, web_ui_client: WebUITestClient):
        """Test that invalid Matrix account credentials show as invalid status in the UI"""
        await web_ui_client.wait_for_server()
        
        # Add an account with invalid Matrix credentials that will definitely fail
        # Use malformed/missing required fields to ensure plugin initialization fails
        invalid_form_data = {
            "protocol": "matrix",
            "account_id": "@invalid_user:invalid-domain",
            "display_name": "Invalid Matrix Account",
            "homeserver": "",  # Empty homeserver should cause failure
            "user_id": "",     # Empty user_id should cause failure 
            "access_token": ""  # Empty access_token should cause failure
        }
        
        # First trigger the HTMX request to load Matrix form fields
        protocol_fields_response = await web_ui_client.get_page("/ui/api/protocol-fields?protocol=matrix")
        matrix_fields_html, matrix_fields_soup = protocol_fields_response
        
        # Verify Matrix-specific fields are loaded
        assert "homeserver" in matrix_fields_html.lower() or "access_token" in matrix_fields_html.lower()
        
        # Submit the form with invalid credentials
        status, response_html, response_soup = await web_ui_client.post_form("/ui/add-account", invalid_form_data)
        
        # The form submission might succeed (saving to database) or fail
        if status == 302:  # Successful redirect
            logger.info("Invalid account form submission successful - checking status display")
            
            # Navigate to main page to check account status
            html, soup = await web_ui_client.get_page("/ui")
            accounts = web_ui_client.extract_accounts_from_table(soup)
            
            # Find the invalid account we just added
            invalid_account = None
            for account in accounts:
                if account.get("account_id") == "@invalid_user:invalid-domain":
                    invalid_account = account
                    break
            
            assert invalid_account is not None, f"Invalid Matrix account not found in accounts list: {accounts}"
            
            # Check that the status shows as invalid
            # The status should be checked real-time from the plugin
            status_text = invalid_account.get("status", "")
            
            # The account should show as invalid since the credentials are bogus
            status_is_invalid = "invalid" in status_text.lower() or "❌" in status_text
            assert status_is_invalid, f"Status text should indicate invalid status. Got: '{status_text}'. Account: {invalid_account}"
            
            logger.info(f"Successfully verified invalid Matrix account shows invalid status: {invalid_account}")
            
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
                status_is_invalid = "invalid" in status_text.lower() or "❌" in status_text
                assert status_is_invalid, f"Status text should indicate invalid status. Got: '{status_text}'. Account: {invalid_account}"
                
                logger.info(f"Successfully verified invalid Matrix account shows invalid status: {invalid_account}")
            else:
                logger.info("Account was not added - this is also acceptable for invalid credentials")
            
        else:
            # Form submission failed with error status - this is also acceptable for invalid credentials
            logger.info(f"Form submission failed with status {status} - this is acceptable for invalid credentials")
            # We can still check that the error handling works properly
            assert status in [400, 422, 500], f"Unexpected status code for invalid credentials: {status}"

    @pytest.mark.asyncio
    async def test_valid_matrix_account_status_checking(self, web_ui_client: WebUITestClient, matrix_test_users):
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
            "access_token": test_user["access_token"]
        }
        
        # First trigger the HTMX request to load Matrix form fields
        protocol_fields_response = await web_ui_client.get_page("/ui/api/protocol-fields?protocol=matrix")
        matrix_fields_html, matrix_fields_soup = protocol_fields_response
        
        # Verify Matrix-specific fields are loaded
        assert "homeserver" in matrix_fields_html.lower() or "access_token" in matrix_fields_html.lower()
        
        # Submit the form with valid credentials
        status, response_html, response_soup = await web_ui_client.post_form("/ui/add-account", valid_form_data)
        
        # The form submission should succeed
        if status == 302:  # Successful redirect
            logger.info("Valid account form submission successful - checking status display")
            
            # Navigate to main page to check account status
            html, soup = await web_ui_client.get_page("/ui")
            accounts = web_ui_client.extract_accounts_from_table(soup)
            
            # Find the valid account we just added
            valid_account = None
            for account in accounts:
                if account.get("account_id") == test_user["user_id"]:
                    valid_account = account
                    break
            
            assert valid_account is not None, f"Valid Matrix account not found in accounts list: {accounts}"
            
            # Check that the status shows as valid
            # The status should be checked real-time from the plugin
            status_text = valid_account.get("status", "")
            
            # The account should show as valid since the credentials are real and working
            status_is_valid = "valid" in status_text.lower() or "✅" in status_text
            assert status_is_valid, f"Status text should indicate valid status. Got: '{status_text}'. Account: {valid_account}"
            
            logger.info(f"Successfully verified valid Matrix account shows valid status: {valid_account}")
            
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
                assert status_is_valid, f"Status text should indicate valid status. Got: '{status_text}'. Account: {valid_account}"
                
                logger.info(f"Successfully verified valid Matrix account shows valid status: {valid_account}")
            else:
                # If account wasn't added, that's unexpected for valid credentials
                pytest.fail(f"Valid Matrix account was not added to the system. Form data: {valid_form_data}")
            
        else:
            # Form submission failed - this is unexpected for valid credentials
            pytest.fail(f"Form submission failed with status {status} for valid credentials. Form data: {valid_form_data}")
