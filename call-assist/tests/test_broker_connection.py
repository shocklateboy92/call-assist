#!/usr/bin/env python3

"""
Quick test to check if the Call Assist broker is running and accessible.
"""

import asyncio
import logging
import socket
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BROKER_HOST = "call-assist-addon"
BROKER_PORT = 50051


async def test_broker_connection():
    """Test if broker is reachable."""
    logger.info(f"🔍 Testing broker connection to {BROKER_HOST}:{BROKER_PORT}")
    
    try:
        # Test basic TCP connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        result = sock.connect_ex((BROKER_HOST, BROKER_PORT))
        sock.close()
        
        if result == 0:
            logger.info("✅ Broker is reachable via TCP")
            return True
        else:
            logger.warning("⚠️  Broker is not reachable via TCP")
            logger.info("   This is expected if broker container is not running")
            return False
            
    except Exception as ex:
        logger.warning(f"⚠️  Failed to connect to broker: {ex}")
        logger.info("   This is expected if broker container is not running")
        return False


if __name__ == "__main__":
    broker_available = asyncio.run(test_broker_connection())
    if broker_available:
        logger.info("✅ Broker is available for testing")
    else:
        logger.info("ℹ️  Broker is not available - integration tests will test config flow only")
    
    sys.exit(0)  # Always exit success - this is just informational