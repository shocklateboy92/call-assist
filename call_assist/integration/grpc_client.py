"""Async gRPC client for Call Assist broker."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf
from grpclib.client import Channel

# Import betterproto generated files
from .proto_gen.callassist.broker import (
    BrokerEntityUpdate,
    BrokerIntegrationStub,
    HaEntityUpdate,
    HealthCheckResponse,
    StartCallRequest,
    StartCallResponse,
)

_LOGGER = logging.getLogger(__name__)


class CallAssistGrpcClient:
    """Async gRPC client for communicating with Call Assist broker."""

    def __init__(self, host: str, port: int):
        """Initialize gRPC client."""
        self.host = host
        self.port = port
        self.target = f"{host}:{port}"
        self.channel: Channel | None = None
        self.stub: BrokerIntegrationStub | None = None
        self._connected = False
        self._max_retries = 5
        self._ha_stream_queue: asyncio.Queue[HaEntityUpdate] = asyncio.Queue()

    async def async_connect(self) -> None:
        """Connect to the gRPC server."""
        if self._connected:
            return

        try:
            self.channel = Channel(host=self.host, port=self.port)
            self.stub = BrokerIntegrationStub(self.channel)
            self._connected = True

            _LOGGER.info("Connected to Call Assist broker at %s", self.target)

        except Exception as ex:
            _LOGGER.error("Failed to connect to broker: %s", ex)
            await self._cleanup()
            raise

    async def async_disconnect(self) -> None:
        """Disconnect from gRPC server."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up connection resources."""
        self._connected = False
        self.stub = None

        if self.channel:
            self.channel.close()
            self.channel = None

    async def ensure_connection(self) -> bool:
        """Ensure connection is active with exponential backoff."""
        if self._connected and self.channel:
            try:
                # Test connection with health check
                await asyncio.wait_for(self.health_check(), timeout=5.0)
                return True
            except Exception:
                self._connected = False

        # Reconnect with exponential backoff
        retry_count = 0
        while retry_count < self._max_retries:
            try:
                await self.async_connect()
                return True
            except Exception as ex:
                retry_count += 1
                wait_time = min(2**retry_count, 30)
                _LOGGER.warning(
                    "Reconnect attempt %d/%d failed: %s. Retrying in %ds",
                    retry_count,
                    self._max_retries,
                    ex,
                    wait_time,
                )
                await asyncio.sleep(wait_time)

        _LOGGER.error("Failed to reconnect after %d attempts", self._max_retries)
        return False

    async def health_check(self) -> HealthCheckResponse:
        """Perform health check with broker."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")

        try:
            request = betterproto_lib_pydantic_google_protobuf.Empty()
            response = await self.stub.health_check(request)
            return response

        except Exception as ex:
            _LOGGER.error("Health check failed: %s", ex)
            raise

    async def send_ha_entity_update(self, entity_data: dict[str, Any]) -> None:
        """Queue an HA entity update to be sent to broker."""
        entity_update = HaEntityUpdate(
            entity_id=entity_data["entity_id"],
            domain=entity_data["domain"],
            name=entity_data["name"],
            state=entity_data["state"],
            attributes=entity_data["attributes"],
            available=entity_data["available"],
            last_updated=entity_data["last_updated"],
        )

        # Add to queue for streaming
        await self._ha_stream_queue.put(entity_update)

    async def stream_ha_entities(self) -> None:
        """Stream HA entity updates to broker."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")

        async def entity_generator() -> AsyncIterator[HaEntityUpdate]:
            """Generate entity updates from queue."""
            while True:
                try:
                    entity_update = await self._ha_stream_queue.get()
                    yield entity_update
                except asyncio.CancelledError:
                    break
                except Exception as ex:
                    _LOGGER.error("Error in entity generator: %s", ex)
                    break

        try:
            await self.stub.stream_ha_entities(entity_generator())
        except Exception as ex:
            _LOGGER.error("Failed to stream HA entities: %s", ex)
            self._connected = False
            raise

    async def stream_broker_entities(self) -> AsyncIterator[BrokerEntityUpdate]:
        """Stream broker entity updates."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")

        try:
            request = betterproto_lib_pydantic_google_protobuf.Empty()
            async for entity_update in self.stub.stream_broker_entities(request):
                yield entity_update

        except Exception:
            _LOGGER.warning("Broker entity streaming connection lost")
            self._connected = False
            raise

    async def start_call(self, call_station_id: str, contact: str) -> StartCallResponse:
        """Start a call using the specified call station and contact."""
        if not self.stub:
            raise RuntimeError("Not connected to broker")

        try:
            request = StartCallRequest(
                call_station_id=call_station_id,
                contact=contact
            )
            response = await self.stub.start_call(request)
            return response

        except Exception as ex:
            _LOGGER.error("Start call failed: %s", ex)
            raise
