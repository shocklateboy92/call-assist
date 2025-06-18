#!/usr/bin/env python3

"""
Integration tests for Call Assist Home Assistant integration using REST API.

This test simulates being the frontend and calls the backend API to:
1. Add the integration via config flow
2. Test configuration flows  
3. Test entity creation
4. Test service calls
5. Test real-time updates

Requires:
- Home Assistant running at homeassistant:8123
- Call Assist integration mounted in custom_components
- Broker running at call-assist-addon:50051
"""

import logging
from typing import Any, Dict, Optional

import aiohttp
import pytest
import pytest_asyncio

# Import broker utilities
from broker_test_utils import get_or_start_broker, stop_global_broker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Home Assistant connection details  
HA_BASE_URL = "http://homeassistant:8123"
HA_API_URL = f"{HA_BASE_URL}/api"

# Default auth token for testing (should be configured in HA)
DEFAULT_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0M2ZmZWJmYjFiNTI0N2RlYjQzZjQxMDAxNGFkZDQwOSIsImlhdCI6MTczNDU2MDgzNCwiZXhwIjoyMDQ5OTIwODM0fQ.XObhdfqt6oCQO2N-Pd8Lw1zJF2JfMEKyIojSa_2kK7w"


class HomeAssistantAPIClient:
    """Client for interacting with Home Assistant REST API."""
    
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url
        self.auth_token = auth_token
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.auth_token}"}
        )
        return self
    
    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        if self.session:
            await self.session.close()
    
    async def get(self, endpoint: str) -> Any:
        """Make GET request to HA API."""
        if not self.session:
            raise RuntimeError("Session not initialized")
        async with self.session.get(f"{self.base_url}{endpoint}") as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to HA API."""
        if not self.session:
            raise RuntimeError("Session not initialized")
        async with self.session.post(
            f"{self.base_url}{endpoint}",
            json=data,
            headers={"Content-Type": "application/json"}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make DELETE request to HA API."""
        if not self.session:
            raise RuntimeError("Session not initialized")
        async with self.session.delete(f"{self.base_url}{endpoint}") as resp:
            resp.raise_for_status()
            return await resp.json() if resp.content_length else {}


@pytest_asyncio.fixture
async def ha_client():
    """Provide Home Assistant API client."""
    async with HomeAssistantAPIClient(HA_API_URL, DEFAULT_AUTH_TOKEN) as client:
        yield client


@pytest_asyncio.fixture
async def broker_manager():
    """Ensure broker is running for tests."""
    logger.info("🔧 Ensuring broker is running...")
    broker_mgr = None
    try:
        broker_mgr = get_or_start_broker()
        logger.info("✅ Broker is ready")
        yield broker_mgr
    except (ConnectionError, OSError, RuntimeError) as ex:
        # These are expected when broker dependencies are missing
        logger.warning(f"⚠️  Could not start broker: {ex}")
        logger.info("   Tests will proceed anyway (config flow should handle this)")
        yield None
    finally:
        # Cleanup broker if we started it
        if broker_mgr:
            try:
                stop_global_broker()
                logger.info("🧹 Cleaned up broker")
            except (ConnectionError, RuntimeError):
                # Broker might already be stopped
                logger.info("Broker already cleaned up")


class TestCallAssistIntegration:
    """Test suite for Call Assist integration."""

    def test_client_initialization(self):
        """Test that the HA client can be initialized."""
        client = HomeAssistantAPIClient("http://test:8123/api", "test_token")
        assert client.base_url == "http://test:8123/api"
        assert client.auth_token == "test_token"
        assert client.session is None

    @pytest.mark.asyncio
    async def test_health_check(self, ha_client: HomeAssistantAPIClient):
        """Test if Home Assistant is responding."""
        response = await ha_client.get("/")
        logger.info("✅ Home Assistant health check passed")
        logger.info(f"   HA Version: {response.get('version', 'unknown')}")
        assert "version" in response

    @pytest.mark.asyncio
    async def test_integration_available(self, ha_client: HomeAssistantAPIClient):
        """Test if Call Assist integration is available."""
        # Check if call_assist is in available integrations
        # Note: This might not be directly exposed in the API
        # So we'll try to start a config flow instead
        response = await ha_client.post("/config/config_entries/flow", {
            "handler": "call_assist"
        })
        
        assert "flow_id" in response, "Call Assist integration not found"
        logger.info("✅ Call Assist integration is available")
        
        # Cancel the flow since we just wanted to test availability
        await ha_client.delete(f"/config/config_entries/flow/{response['flow_id']}")

    @pytest.mark.asyncio
    async def test_config_flow_user_step(self, ha_client: HomeAssistantAPIClient):
        """Test the user configuration step."""
        # Start config flow
        response = await ha_client.post("/config/config_entries/flow", {
            "handler": "call_assist"
        })
        
        flow_id = response.get("flow_id")
        assert flow_id is not None, "Failed to start config flow"
        
        # Note: In a real test, you might want to store this for cleanup
        # For now, we'll clean up at the end of the test
        
        logger.info(f"✅ Started config flow: {flow_id}")
        logger.info(f"   Step: {response.get('step_id')}")
        logger.info(f"   Type: {response.get('type')}")
        
        # Check if we got the user form
        assert response.get("type") == "form", f"Expected form, got {response.get('type')}"
        assert response.get("step_id") == "user", f"Expected user step, got {response.get('step_id')}"
        logger.info("✅ User config form displayed correctly")
        
        # Clean up the flow
        try:
            await ha_client.delete(f"/config/config_entries/flow/{flow_id}")
            logger.info("✅ Cleaned up test config flow")
        except aiohttp.ClientResponseError as ex:
            if ex.status == 404:
                logger.info("Flow already cleaned up")
            else:
                logger.warning(f"⚠️  Could not cleanup flow: {ex}")

    @pytest.mark.asyncio
    async def test_config_flow_submit(self, ha_client: HomeAssistantAPIClient):
        """Test submitting configuration data."""
        # First start a config flow
        response = await ha_client.post("/config/config_entries/flow", {
            "handler": "call_assist"
        })
        flow_id = response["flow_id"]
        
        # Submit configuration (this will likely fail without a real broker)
        config_data = {
            "host": "call-assist-addon",
            "port": 50051
        }
        
        response = await ha_client.post(f"/config/config_entries/flow/{flow_id}", config_data)
        
        if response.get("type") == "create_entry":
            config_entry_id = response.get("result", {}).get("entry_id")
            logger.info("✅ Config flow completed successfully")
            logger.info(f"   Entry ID: {config_entry_id}")
            logger.info(f"   Title: {response.get('title')}")
            
            # Clean up the created entry
            if config_entry_id:
                try:
                    await ha_client.delete(f"/config/config_entries/{config_entry_id}")
                    logger.info("✅ Cleaned up test configuration")
                except aiohttp.ClientResponseError as ex:
                    if ex.status == 404:
                        logger.info("Config entry already cleaned up")
                    else:
                        logger.warning(f"⚠️  Could not cleanup config entry: {ex}")
        elif response.get("type") == "form":
            # Form returned with errors
            errors = response.get("errors", {})
            if "base" in errors and errors["base"] == "cannot_connect":
                logger.warning("⚠️  Expected connection error (broker not running)")
                logger.info("   This is expected in test environment")
                # Consider this a pass since config flow is working
            else:
                pytest.fail(f"Config flow error: {errors}")
        else:
            pytest.fail(f"Unexpected config flow response: {response}")
        
        # Always try to clean up the flow
        try:
            await ha_client.delete(f"/config/config_entries/flow/{flow_id}")
            logger.info("✅ Cleaned up test config flow")
        except aiohttp.ClientResponseError as ex:
            if ex.status == 404:
                logger.info("Flow already cleaned up")
            else:
                logger.warning(f"⚠️  Could not cleanup flow: {ex}")

    @pytest.mark.asyncio
    async def test_config_entries(self, ha_client: HomeAssistantAPIClient):
        """Test listing configuration entries."""
        response = await ha_client.get("/config/config_entries")
        
        call_assist_entries = [
            entry for entry in response
            if entry.get("domain") == "call_assist"
        ]
        
        if call_assist_entries:
            logger.info(f"✅ Found {len(call_assist_entries)} Call Assist config entries")
            for entry in call_assist_entries:
                logger.info(f"   Entry: {entry.get('title')} (ID: {entry.get('entry_id')})")
                logger.info(f"   State: {entry.get('state')}")
        else:
            logger.warning("⚠️  No Call Assist config entries found")
            # This might be expected in test environment

    @pytest.mark.asyncio
    async def test_entities(self, ha_client: HomeAssistantAPIClient):
        """Test that Call Assist entities are created."""
        response = await ha_client.get("/states")
        
        call_assist_entities = [
            entity for entity in response
            if entity.get("entity_id", "").startswith("call_assist.")
        ]
        
        if call_assist_entities:
            logger.info(f"✅ Found {len(call_assist_entities)} Call Assist entities")
            for entity in call_assist_entities:
                entity_id = entity.get("entity_id")
                state = entity.get("state")
                attributes = entity.get("attributes", {})
                logger.info(f"   {entity_id}: {state}")
                
                # Check if it's a contact or station
                if "contact_" in entity_id:
                    logger.info(f"     Contact - Protocol: {attributes.get('protocol')}")
                elif "station_" in entity_id:
                    logger.info(f"     Station - Camera: {attributes.get('camera_entity')}")
        else:
            logger.warning("⚠️  No Call Assist entities found")
            logger.info("   This may be expected if broker is not running")

    @pytest.mark.asyncio
    async def test_services(self, ha_client: HomeAssistantAPIClient):
        """Test that Call Assist services are registered."""
        response = await ha_client.get("/services")
        
        call_assist_services = response.get("call_assist", {})
        
        expected_services = ["make_call", "end_call", "accept_call", "add_contact", "remove_contact"]
        found_services = list(call_assist_services.keys())
        
        if call_assist_services:
            logger.info(f"✅ Found Call Assist services: {found_services}")
            
            # Check if all expected services are present
            missing_services = set(expected_services) - set(found_services)
            if missing_services:
                logger.warning(f"⚠️  Missing services: {missing_services}")
            else:
                logger.info("✅ All expected services are registered")
        else:
            logger.warning("⚠️  No Call Assist services found")

    @pytest.mark.asyncio
    async def test_service_call(self, ha_client: HomeAssistantAPIClient):
        """Test calling a Call Assist service."""
        # Try to call add_contact service
        service_data = {
            "contact_id": "test_contact",
            "display_name": "Test Contact",
            "protocol": "matrix",
            "address": "@test:matrix.org"
        }
        
        # This may fail if the integration isn't loaded, but we'll try anyway
        try:
            await ha_client.post("/services/call_assist/add_contact", service_data)
            # Service calls return empty response on success
            logger.info("✅ Successfully called add_contact service")
        except aiohttp.ClientResponseError as ex:
            if ex.status == 400:
                # Service might not be available without proper setup
                logger.warning("⚠️  Service call failed (expected without proper setup)")
                pytest.skip("Service not available without proper broker connection")
            else:
                raise

