#!/usr/bin/env python3

"""
Test script to verify plugin manager and schema integration
"""

import asyncio
import sys
import os
import logging

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from addon.broker.plugin_manager import PluginManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_plugin_schema_integration():
    """Test that plugin manager loads schemas correctly"""
    logger.info("Testing plugin manager schema integration...")
    
    # Initialize plugin manager
    plugin_manager = PluginManager()
    
    # Check that plugins were discovered
    available_protocols = plugin_manager.get_available_protocols()
    logger.info(f"Available protocols: {available_protocols}")
    
    if not available_protocols:
        logger.warning("No plugins found!")
        return False
    
    # Get protocol schemas
    schemas = plugin_manager.get_protocol_schemas()
    logger.info(f"Generated schemas for {len(schemas)} protocols")
    
    # Test schema structure for each protocol
    for protocol, schema in schemas.items():
        logger.info(f"\n=== Protocol: {protocol} ===")
        logger.info(f"Display Name: {schema['display_name']}")
        logger.info(f"Description: {schema['description']}")
        
        logger.info(f"Credential Fields ({len(schema['credential_fields'])}):")
        for field in schema['credential_fields']:
            logger.info(f"  - {field['key']}: {field['display_name']} ({field['type']}, required={field['required']})")
        
        logger.info(f"Setting Fields ({len(schema['setting_fields'])}):")
        for field in schema['setting_fields']:
            logger.info(f"  - {field['key']}: {field['display_name']} ({field['type']}, required={field['required']})")
        
        logger.info(f"Example Account IDs: {schema['example_account_ids']}")
    
    logger.info("\n✅ Plugin schema integration test passed!")
    return True


async def test_broker_schema_endpoint():
    """Test that broker can provide schemas via gRPC"""
    logger.info("Testing broker schema endpoint...")
    
    try:
        from addon.broker.main import CallAssistBroker
        import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
        
        # Create broker instance
        broker = CallAssistBroker()
        
        # Test get_protocol_schemas
        response = await broker.get_protocol_schemas(betterproto_lib_google.Empty())
        
        logger.info(f"Broker returned {len(response.schemas)} protocol schemas")
        
        for schema in response.schemas:
            logger.info(f"\n=== Protocol: {schema.protocol} ===")
            logger.info(f"Display Name: {schema.display_name}")
            logger.info(f"Description: {schema.description}")
            logger.info(f"Credential Fields: {len(schema.credential_fields)}")
            logger.info(f"Setting Fields: {len(schema.setting_fields)}")
        
        logger.info("\n✅ Broker schema endpoint test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Broker schema endpoint test failed: {e}")
        return False


async def main():
    """Run all tests"""
    logger.info("Starting plugin integration tests...\n")
    
    success = True
    
    # Test 1: Plugin Manager Schema Generation
    if not await test_plugin_schema_integration():
        success = False
    
    # Test 2: Broker Schema Endpoint
    if not await test_broker_schema_endpoint():
        success = False
    
    if success:
        logger.info("\n🎉 All tests passed! Plugin integration is working correctly.")
    else:
        logger.error("\n❌ Some tests failed. Check the logs above.")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
