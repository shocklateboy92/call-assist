#!/usr/bin/env python3

"""
Test that the broker can start up properly with all integrated components
"""

import asyncio
import logging
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_broker_startup():
    """Test that broker starts up correctly with plugin manager integration"""
    logger.info("Testing broker startup with integrated components...")
    
    # Set up database path for testing
    db_path = "/tmp/test_call_assist.db"
    
    try:
        from addon.broker.main import CallAssistBroker
        from addon.broker.database import set_database_path
        
        set_database_path(db_path)
        
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
        
        # Test gRPC schema endpoint
        import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
        response = await broker.get_protocol_schemas(betterproto_lib_google.Empty())
        assert len(response.schemas) > 0, "gRPC endpoint returned no schemas"
        logger.info(f"✅ gRPC endpoint returned {len(response.schemas)} schemas")
        
        # Test health check still works
        health = await broker.health_check(betterproto_lib_google.Empty())
        assert health.healthy, "Health check failed"
        logger.info("✅ Health check passed")
        
        logger.info("🎉 Broker startup test passed! All components integrated successfully.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Broker startup test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test database
        if os.path.exists(db_path):
            os.remove(db_path)


async def main():
    """Run broker startup test"""
    success = await test_broker_startup()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
