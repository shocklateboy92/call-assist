#!/usr/bin/env python3
"""Test script for account management functionality."""

import asyncio
import logging
import sys
import os

# Add the integration directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from grpc_client import CallAssistGrpcClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_account_management():
    """Test account management functionality."""
    client = CallAssistGrpcClient("localhost", 50051)
    
    try:
        # Connect to broker
        logger.info("Connecting to broker...")
        await client.async_connect()
        
        # Test adding a Matrix account
        logger.info("Adding Matrix account...")
        matrix_credentials = {
            "homeserver": "https://matrix.org",
            "access_token": "test_token_123",
            "user_id": "@testuser:matrix.org"
        }
        
        success = await client.add_account(
            protocol="matrix",
            account_id="@testuser:matrix.org",
            display_name="Test Matrix Account",
            credentials=matrix_credentials
        )
        
        logger.info(f"Matrix account added: {success}")
        
        # Test adding an XMPP account
        logger.info("Adding XMPP account...")
        xmpp_credentials = {
            "username": "testuser",
            "password": "testpass",
            "server": "jabber.org",
            "port": "5222"
        }
        
        success = await client.add_account(
            protocol="xmpp",
            account_id="testuser@jabber.org",
            display_name="Test XMPP Account",
            credentials=xmpp_credentials
        )
        
        logger.info(f"XMPP account added: {success}")
        
        # Get configured accounts
        logger.info("Getting configured accounts...")
        accounts = await client.get_configured_accounts()
        
        logger.info("Configured accounts:")
        for key, account in accounts.items():
            logger.info(f"  {key}: {account['display_name']} ({account['protocol']}) - Available: {account['available']}")
        
        # Test system status
        logger.info("Getting system status...")
        status = await client.async_get_status()
        
        logger.info(f"Broker version: {status.get('version')}")
        logger.info(f"Call stations: {len(status.get('call_stations', []))}")
        logger.info(f"Contacts: {len(status.get('contacts', []))}")
        logger.info(f"Available plugins: {len(status.get('available_plugins', []))}")
        
        await client.async_disconnect()
        logger.info("Test completed successfully!")
        
    except Exception as ex:
        logger.error(f"Test failed: {ex}")
        await client.async_disconnect()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_account_management())
    sys.exit(0 if success else 1)