#!/usr/bin/env python3

"""
Test that the broker can start up properly with all integrated components
"""

import asyncio
import logging
import os
import sys
import tempfile

from addon.broker.broker import CallAssistBroker
from addon.broker.dependencies import get_app_state

logger = logging.getLogger(__name__)


async def test_broker_startup():
    """Test that broker starts up correctly with plugin manager integration"""
    logger.info("Testing broker startup with integrated components...")

    # Set up database path for testing
    db_path = tempfile.mktemp()

    try:
        get_app_state().db_path = db_path

        # Create broker instance
        broker = CallAssistBroker()

        # Test that plugin manager is initialized
        assert broker.plugin_manager is not None, "Plugin manager not initialized"
        logger.info("✅ Plugin manager initialized")

        # Test that plugins are discovered
        protocols = broker.plugin_manager.get_available_protocols()
        logger.info(f"✅ Found {len(protocols)} protocols: {protocols}")

        # Test that schemas can be generated
        schemas = broker.plugin_manager.get_protocol_schemas()
        assert len(schemas) > 0, "No schemas generated"
        logger.info(f"✅ Generated {len(schemas)} protocol schemas")

        # Test that web UI can access schemas through broker
        # (This simulates what the web UI does)
        ui_schemas = broker.plugin_manager.get_protocol_schemas()
        assert len(ui_schemas) > 0, "Web UI cannot access schemas"
        logger.info("✅ Web UI can access schemas through broker")

        # Test health check still works
        import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
        health = await broker.health_check(betterproto_lib_google.Empty())
        assert health.healthy, "Health check failed"
        logger.info("✅ Health check passed")

        logger.info("🎉 Broker startup test passed! All components integrated successfully.")
        return True

    finally:
        # Clean up test database
        if os.path.exists(db_path):
            os.remove(db_path)

        return False


async def main():
    """Run broker startup test"""
    return await test_broker_startup()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
