#!/usr/bin/env python3
"""
Test script for dynamic service registration flow.

This script tests:
1. Broker service registry
2. gRPC service definitions 
3. Service execution

Run this with the broker running.
"""

import asyncio
import logging
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from proto_gen.callassist.broker import (
    BrokerIntegrationStub,
    ServiceExecutionRequest,
)
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf
from grpclib.client import Channel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_dynamic_services():
    """Test the dynamic service registration flow."""
    
    # Connect to broker
    channel = Channel(host="localhost", port=50051)
    stub = BrokerIntegrationStub(channel)
    
    try:
        # Test 1: Health check
        logger.info("Testing broker connection...")
        health_response = await stub.health_check(betterproto_lib_pydantic_google_protobuf.Empty())
        logger.info(f"Broker health: {health_response.healthy} - {health_response.message}")
        
        # Test 2: Get service definitions
        logger.info("Getting service definitions...")
        service_count = 0
        async for service_def in stub.get_service_definitions(betterproto_lib_pydantic_google_protobuf.Empty()):
            logger.info(f"Service: {service_def.service_name}")
            logger.info(f"  Display Name: {service_def.display_name}")
            logger.info(f"  Description: {service_def.description}")
            logger.info(f"  Fields: {len(service_def.fields)}")
            logger.info(f"  Icon: {service_def.icon}")
            logger.info(f"  Required Capabilities: {service_def.required_capabilities}")
            for field in service_def.fields:
                logger.info(f"    - {field.key}: {field.field_type.name} ({field.display_name})")
                logger.info(f"      Description: {field.description}")
                logger.info(f"      Required: {field.required}")
                logger.info(f"      Options: {field.options}")
                logger.info(f"      Default: {field.default_value}")
            service_count += 1
        
        logger.info(f"Found {service_count} services")
        
        # Test 3: Execute make_call service
        if service_count > 0:
            logger.info("Testing service execution...")
            request = ServiceExecutionRequest(
                service_name="makecall",  # Use the actual registered name
                parameters={
                    "call_station_id": "living_room:Living Room",
                    "contact_id": "family_room:Family Room", 
                    "duration_minutes": "15"
                },
                integration_id="test_script"
            )
            
            response = await stub.execute_service(request)
            logger.info(f"Service execution result: {response.success}")
            logger.info(f"Message: {response.message}")
            if response.result_data:
                logger.info(f"Result data: {response.result_data}")
        
        logger.info("Test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        channel.close()


if __name__ == "__main__":
    asyncio.run(test_dynamic_services())
