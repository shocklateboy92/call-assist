#!/usr/bin/env python3

"""
Test script to verify plugin manager and schema integration
"""

import asyncio
import logging
import os
import sys

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from addon.broker.plugin_manager import PluginManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_plugin_schema_integration() -> bool:
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
        for field in schema["credential_fields"]:
            logger.info(
                f"  - {field['key']}: {field['display_name']} ({field['type']}, required={field['required']})"
            )

        logger.info(f"Setting Fields ({len(schema['setting_fields'])}):")
        for field in schema["setting_fields"]:
            logger.info(
                f"  - {field['key']}: {field['display_name']} ({field['type']}, required={field['required']})"
            )

        logger.info(f"Example Account IDs: {schema['example_account_ids']}")

    logger.info("\n✅ Plugin schema integration test passed!")
    return True


async def test_broker_plugin_integration() -> bool:
    """Test that broker integrates correctly with plugin manager"""
    logger.info("Testing broker plugin integration...")

    try:
        from addon.broker.broker import CallAssistBroker

        # Create broker instance
        broker = CallAssistBroker()

        # Test that plugin manager is initialized
        assert broker.plugin_manager is not None, "Plugin manager not initialized"
        logger.info("✅ Plugin manager properly integrated with broker")

        # Test that web UI can access schemas through broker
        schemas = broker.plugin_manager.get_protocol_schemas()
        logger.info(
            f"✅ Web UI can access {len(schemas)} protocol schemas through broker"
        )

        for protocol, schema in schemas.items():
            logger.info(f"  - {protocol}: {schema['display_name']}")

        logger.info("✅ Broker plugin integration test passed!")
        return True

    except Exception as e:
        logger.error(f"❌ Broker plugin integration test failed: {e}")
        return False


async def main() -> bool:
    """Run all tests"""
    logger.info("Starting plugin integration tests...\n")

    success = True

    # Test 1: Plugin Manager Schema Generation
    if not await test_plugin_schema_integration():
        success = False

    # Test 2: Broker Plugin Integration
    if not await test_broker_plugin_integration():
        success = False

    if success:
        logger.info("\n🎉 All tests passed! Plugin integration is working correctly.")
    else:
        logger.error("\n❌ Some tests failed. Check the logs above.")

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
