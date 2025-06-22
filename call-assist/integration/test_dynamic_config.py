#!/usr/bin/env python3
"""Test script for data-driven configuration flows."""

import asyncio
import logging
import sys
import os

# Add the integration directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from grpc_client import CallAssistGrpcClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_protocol_schemas():
    """Test protocol schema retrieval."""
    client = CallAssistGrpcClient("localhost", 50051)
    
    try:
        # Connect to broker
        logger.info("Connecting to broker...")
        await client.async_connect()
        
        # Get protocol schemas
        logger.info("Getting protocol schemas...")
        schemas = await client.get_protocol_schemas()
        
        logger.info(f"Found {len(schemas)} protocol schemas:")
        
        for protocol, schema in schemas.items():
            logger.info(f"\\n=== {schema['display_name']} ({protocol}) ===")
            logger.info(f"Description: {schema['description']}")
            
            logger.info("Credential fields:")
            for field in schema['credential_fields']:
                required = "required" if field['required'] else "optional"
                sensitive = " (sensitive)" if field['sensitive'] else ""
                default = f" [default: {field['default_value']}]" if field['default_value'] else ""
                logger.info(f"  • {field['display_name']} ({field['key']}) - {required}{sensitive}{default}")
                logger.info(f"    {field['description']}")
            
            if schema['setting_fields']:
                logger.info("Setting fields:")
                for field in schema['setting_fields']:
                    required = "required" if field['required'] else "optional"
                    default = f" [default: {field['default_value']}]" if field['default_value'] else ""
                    allowed = f" [options: {', '.join(field['allowed_values'])}]" if field['allowed_values'] else ""
                    logger.info(f"  • {field['display_name']} ({field['key']}) - {required}{default}{allowed}")
                    logger.info(f"    {field['description']}")
            
            if schema['example_account_ids']:
                logger.info(f"Example account IDs: {', '.join(schema['example_account_ids'])}")
        
        await client.async_disconnect()
        logger.info("\\nSchema test completed successfully!")
        
    except Exception as ex:
        logger.error(f"Schema test failed: {ex}")
        await client.async_disconnect()
        return False
    
    return True


async def test_dynamic_account_creation():
    """Test creating accounts using dynamic schemas."""
    client = CallAssistGrpcClient("localhost", 50051)
    
    try:
        await client.async_connect()
        
        # Get schemas first
        schemas = await client.get_protocol_schemas()
        
        # Test Matrix account creation
        if "matrix" in schemas:
            logger.info("\\nTesting Matrix account creation with dynamic schema...")
            matrix_schema = schemas["matrix"]
            
            # Build credentials from schema
            credentials = {}
            for field in matrix_schema["credential_fields"]:
                if field["key"] == "homeserver":
                    credentials[field["key"]] = field.get("default_value", "https://matrix.org")
                elif field["key"] == "access_token":
                    credentials[field["key"]] = "test_dynamic_token_123"
                elif field["key"] == "user_id":
                    credentials[field["key"]] = "@testdynamic:matrix.org"
            
            success = await client.add_account(
                protocol="matrix",
                account_id=credentials["user_id"],
                display_name="Dynamic Test Matrix",
                credentials=credentials
            )
            logger.info(f"Dynamic Matrix account creation: {success}")
        
        # Test XMPP account creation
        if "xmpp" in schemas:
            logger.info("\\nTesting XMPP account creation with dynamic schema...")
            xmpp_schema = schemas["xmpp"]
            
            # Build credentials from schema
            credentials = {}
            for field in xmpp_schema["credential_fields"]:
                if field["key"] == "username":
                    credentials[field["key"]] = "testdynamic"
                elif field["key"] == "password":
                    credentials[field["key"]] = "testpass123"
                elif field["key"] == "server":
                    credentials[field["key"]] = "jabber.org"
                elif field["key"] == "port":
                    credentials[field["key"]] = field.get("default_value", "5222")
            
            account_id = f"{credentials['username']}@{credentials['server']}"
            
            success = await client.add_account(
                protocol="xmpp",
                account_id=account_id,
                display_name="Dynamic Test XMPP",
                credentials=credentials
            )
            logger.info(f"Dynamic XMPP account creation: {success}")
        
        # Show final account list
        logger.info("\\nFinal configured accounts:")
        accounts = await client.get_configured_accounts()
        for key, account in accounts.items():
            status = "✓" if account["available"] else "✗"
            logger.info(f"  {status} {account['display_name']} ({account['protocol']}) - {account['account_id']}")
        
        await client.async_disconnect()
        logger.info("\\nDynamic account creation test completed!")
        
    except Exception as ex:
        logger.error(f"Dynamic account creation test failed: {ex}")
        await client.async_disconnect()
        return False
    
    return True


if __name__ == "__main__":
    async def run_tests():
        logger.info("=== Testing Data-Driven Configuration ===\\n")
        
        schema_success = await test_protocol_schemas()
        if not schema_success:
            return False
        
        account_success = await test_dynamic_account_creation()
        return account_success
    
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)