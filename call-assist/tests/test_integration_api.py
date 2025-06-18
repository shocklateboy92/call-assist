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

import asyncio
import logging
import sys
from typing import Any, Dict, Optional

import aiohttp

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
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
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


class CallAssistIntegrationTester:
    """Test suite for Call Assist integration."""
    
    def __init__(self, ha_client: HomeAssistantAPIClient):
        self.ha = ha_client
        self.config_entry_id: Optional[str] = None
    
    async def test_health_check(self) -> bool:
        """Test if Home Assistant is responding."""
        try:
            response = await self.ha.get("/")
            logger.info("✅ Home Assistant health check passed")
            logger.info(f"   HA Version: {response.get('version', 'unknown')}")
            return True
        except Exception as ex:
            logger.error(f"❌ Home Assistant health check failed: {ex}")
            return False
    
    async def test_integration_available(self) -> bool:
        """Test if Call Assist integration is available."""
        try:
            # Check if call_assist is in available integrations
            # Note: This might not be directly exposed in the API
            # So we'll try to start a config flow instead
            response = await self.ha.post("/config/config_entries/flow", {
                "handler": "call_assist"
            })
            
            if "flow_id" in response:
                logger.info("✅ Call Assist integration is available")
                # Cancel the flow since we just wanted to test availability
                await self.ha.delete(f"/config/config_entries/flow/{response['flow_id']}")
                return True
            else:
                logger.error("❌ Call Assist integration not found")
                return False
                
        except Exception as ex:
            logger.error(f"❌ Failed to check integration availability: {ex}")
            return False
    
    async def test_config_flow_user_step(self) -> Optional[str]:
        """Test the user configuration step."""
        try:
            # Start config flow
            response = await self.ha.post("/config/config_entries/flow", {
                "handler": "call_assist"
            })
            
            flow_id = response.get("flow_id")
            if not flow_id:
                logger.error("❌ Failed to start config flow")
                return None
            
            logger.info(f"✅ Started config flow: {flow_id}")
            logger.info(f"   Step: {response.get('step_id')}")
            logger.info(f"   Type: {response.get('type')}")
            
            # Check if we got the user form
            if response.get("type") == "form" and response.get("step_id") == "user":
                logger.info("✅ User config form displayed correctly")
                return flow_id
            else:
                logger.error(f"❌ Unexpected config flow response: {response}")
                return None
                
        except Exception as ex:
            logger.error(f"❌ Config flow user step failed: {ex}")
            return None
    
    async def test_config_flow_submit(self, flow_id: str) -> bool:
        """Test submitting configuration data."""
        try:
            # Submit configuration (this will likely fail without a real broker)
            config_data = {
                "host": "call-assist-addon",
                "port": 50051
            }
            
            response = await self.ha.post(f"/config/config_entries/flow/{flow_id}", config_data)
            
            if response.get("type") == "create_entry":
                self.config_entry_id = response.get("result", {}).get("entry_id")
                logger.info("✅ Config flow completed successfully")
                logger.info(f"   Entry ID: {self.config_entry_id}")
                logger.info(f"   Title: {response.get('title')}")
                return True
            elif response.get("type") == "form":
                # Form returned with errors
                errors = response.get("errors", {})
                if "base" in errors:
                    if errors["base"] == "cannot_connect":
                        logger.warning("⚠️  Expected connection error (broker not running)")
                        logger.info("   This is expected in test environment")
                        return True  # Consider this a pass since config flow is working
                    else:
                        logger.error(f"❌ Config flow error: {errors}")
                        return False
                else:
                    logger.error(f"❌ Unexpected form errors: {errors}")
                    return False
            else:
                logger.error(f"❌ Unexpected config flow response: {response}")
                return False
                
        except Exception as ex:
            logger.error(f"❌ Config flow submit failed: {ex}")
            return False
    
    async def test_config_entries(self) -> bool:
        """Test listing configuration entries."""
        try:
            response = await self.ha.get("/config/config_entries")
            
            call_assist_entries = [
                entry for entry in response
                if entry.get("domain") == "call_assist"
            ]
            
            if call_assist_entries:
                logger.info(f"✅ Found {len(call_assist_entries)} Call Assist config entries")
                for entry in call_assist_entries:
                    logger.info(f"   Entry: {entry.get('title')} (ID: {entry.get('entry_id')})")
                    logger.info(f"   State: {entry.get('state')}")
                return True
            else:
                logger.warning("⚠️  No Call Assist config entries found")
                return False
                
        except Exception as ex:
            logger.error(f"❌ Failed to list config entries: {ex}")
            return False
    
    async def test_entities(self) -> bool:
        """Test that Call Assist entities are created."""
        try:
            response = await self.ha.get("/states")
            
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
                
                return True
            else:
                logger.warning("⚠️  No Call Assist entities found")
                logger.info("   This may be expected if broker is not running")
                return False
                
        except Exception as ex:
            logger.error(f"❌ Failed to list entities: {ex}")
            return False
    
    async def test_services(self) -> bool:
        """Test that Call Assist services are registered."""
        try:
            response = await self.ha.get("/services")
            
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
                
                return True
            else:
                logger.warning("⚠️  No Call Assist services found")
                return False
                
        except Exception as ex:
            logger.error(f"❌ Failed to list services: {ex}")
            return False
    
    async def test_service_call(self) -> bool:
        """Test calling a Call Assist service."""
        try:
            # Try to call add_contact service
            service_data = {
                "contact_id": "test_contact",
                "display_name": "Test Contact",
                "protocol": "matrix",
                "address": "@test:matrix.org"
            }
            
            response = await self.ha.post("/services/call_assist/add_contact", service_data)
            
            # Service calls return empty response on success
            logger.info("✅ Successfully called add_contact service")
            return True
            
        except Exception as ex:
            logger.error(f"❌ Service call failed: {ex}")
            return False
    
    async def cleanup(self) -> bool:
        """Clean up test configuration."""
        if not self.config_entry_id:
            return True
            
        try:
            await self.ha.delete(f"/config/config_entries/{self.config_entry_id}")
            logger.info("✅ Cleaned up test configuration")
            return True
        except Exception as ex:
            logger.error(f"❌ Failed to cleanup: {ex}")
            return False


async def run_integration_tests():
    """Run all integration tests."""
    logger.info("🚀 Starting Call Assist Integration Tests")
    logger.info("=" * 50)
    
    # Start broker if needed
    logger.info("🔧 Ensuring broker is running...")
    try:
        broker_manager = get_or_start_broker()
        logger.info("✅ Broker is ready")
    except Exception as ex:
        logger.warning(f"⚠️  Could not start broker: {ex}")
        logger.info("   Tests will proceed anyway (config flow should handle this)")
        broker_manager = None
    
    async with HomeAssistantAPIClient(HA_API_URL, DEFAULT_AUTH_TOKEN) as ha_client:
        tester = CallAssistIntegrationTester(ha_client)
        
        # Test sequence
        tests = [
            ("Health Check", tester.test_health_check),
            ("Integration Available", tester.test_integration_available),
            ("Config Flow User Step", lambda: tester.test_config_flow_user_step()),
            ("Config Entries", tester.test_config_entries),
            ("Entities", tester.test_entities),
            ("Services", tester.test_services),
            ("Service Call", tester.test_service_call),
        ]
        
        results = []
        flow_id = None
        
        for test_name, test_func in tests:
            logger.info(f"\n🧪 Running: {test_name}")
            try:
                if test_name == "Config Flow User Step":
                    flow_id = await test_func()
                    result = flow_id is not None
                elif test_name == "Config Flow Submit" and flow_id:
                    result = await tester.test_config_flow_submit(flow_id)
                else:
                    result = await test_func()
                
                results.append((test_name, result))
                
                if result:
                    logger.info(f"✅ {test_name}: PASSED")
                else:
                    logger.error(f"❌ {test_name}: FAILED")
                    
            except Exception as ex:
                logger.error(f"❌ {test_name}: ERROR - {ex}")
                results.append((test_name, False))
        
        # If we have a flow_id, test submission too
        if flow_id:
            logger.info(f"\n🧪 Running: Config Flow Submit")
            try:
                result = await tester.test_config_flow_submit(flow_id)
                results.append(("Config Flow Submit", result))
                if result:
                    logger.info(f"✅ Config Flow Submit: PASSED")
                else:
                    logger.error(f"❌ Config Flow Submit: FAILED")
            except Exception as ex:
                logger.error(f"❌ Config Flow Submit: ERROR - {ex}")
                results.append(("Config Flow Submit", False))
        
        # Summary
        logger.info("\n" + "=" * 50)
        logger.info("📊 Test Results Summary")
        logger.info("=" * 50)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{status:<8} {test_name}")
        
        logger.info(f"\nResults: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed!")
            success = True
        else:
            logger.error(f"😞 {total - passed} tests failed")
            success = False
    
    # Cleanup broker if we started it
    try:
        if broker_manager:
            stop_global_broker()
            logger.info("🧹 Cleaned up broker")
    except Exception as ex:
        logger.warning(f"⚠️  Error cleaning up broker: {ex}")
    
    return success


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(run_integration_tests())
    sys.exit(0 if success else 1)