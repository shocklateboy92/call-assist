#!/usr/bin/env python3
"""Test for the start_call service functionality"""

import logging

import pytest
from proto_gen.callassist.broker import (
    BrokerIntegrationStub,
    StartCallRequest,
    StartCallResponse,
)
from .types import BrokerProcessInfo
from grpclib.client import Channel

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_start_call_via_grpc(broker_process: BrokerProcessInfo) -> None:
    """Test start_call functionality using full broker with gRPC"""
    grpc_port = broker_process.grpc_port

    # Connect to broker
    channel = Channel("localhost", grpc_port)
    stub = BrokerIntegrationStub(channel)

    try:
        # Test with invalid call station first to verify error handling
        request = StartCallRequest(
            call_station_id="invalid_station_id",
            contact="@test_user:matrix.org"
        )

        response = await stub.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert response.success == False
        assert "not found" in response.message
        assert response.call_id == ""

        logger.info(f"✅ Invalid station test successful: {response.message}")

    finally:
        channel.close()


@pytest.mark.asyncio
async def test_start_call_invalid_station_via_grpc(broker_process: BrokerProcessInfo) -> None:
    """Test start_call with invalid call station ID"""
    grpc_port = broker_process.grpc_port

    # Connect to broker
    channel = Channel("localhost", grpc_port)
    stub = BrokerIntegrationStub(channel)

    try:
        request = StartCallRequest(
            call_station_id="invalid_station_id",
            contact="@test_user:matrix.org"
        )

        response = await stub.start_call(request)

        assert isinstance(response, StartCallResponse)
        assert response.success == False
        assert "not found" in response.message
        assert response.call_id == ""

        logger.info(f"✅ Invalid station test successful: {response.message}")

    finally:
        channel.close()
