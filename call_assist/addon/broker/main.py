#!/usr/bin/env python3

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
from grpclib.server import Server

from addon.broker.dependencies import app_state
from addon.broker.plugin_manager import PluginManager
from addon.broker.queries import get_enabled_call_stations_with_session
from addon.broker.web_server import WebUIServer

# Import betterproto generated classes
from proto_gen.callassist.broker import (
    BrokerEntityType,
    BrokerEntityUpdate,
    BrokerIntegrationBase,
    HaEntityUpdate,
    HealthCheckResponse,
    StartCallRequest,
    StartCallResponse,
)

if TYPE_CHECKING:
    # Forward reference for type hints
    pass

logger = logging.getLogger(__name__)

# FastAPI-based broker using dependency injection


@dataclass
class HAEntity:
    """Represents a Home Assistant entity we're monitoring"""

    entity_id: str
    domain: str
    name: str
    state: str
    attributes: dict[str, str]
    available: bool
    last_updated: datetime


@dataclass
class CallStation:
    """Represents a call station (camera + media player combination)"""

    station_id: str
    name: str
    camera_entity_id: str
    media_player_entity_id: str
    state: str = "idle"
    available: bool = True

    @property
    def attributes(self) -> dict[str, str]:
        return {
            "camera_entity": self.camera_entity_id,
            "media_player_entity": self.media_player_entity_id,
            "station_type": "call_station",
        }


class CallAssistBroker(BrokerIntegrationBase):
    """
    Simplified broker service that implements the new interface:
    - Receives HA entity streams
    - Provides broker entity streams
    - Basic health check
    """

    def __init__(self, plugin_manager: PluginManager | None = None, database_manager=None):
        # Store HA entities we receive
        self.ha_entities: dict[str, HAEntity] = {}

        # Store call stations we create
        self.call_stations: dict[str, CallStation] = {}

        # Track broker entity update subscribers
        self.broker_entity_subscribers: list[asyncio.Queue] = []

        # Startup time for health check
        self.startup_time = datetime.now(UTC)

        # Initialize plugin manager (injected or create new)
        self.plugin_manager = plugin_manager or PluginManager()

        # Store database manager reference (injected or None)
        self.database_manager = database_manager

    async def stream_ha_entities(
        self, ha_entity_update_iterator: AsyncIterator[HaEntityUpdate]
    ) -> betterproto_lib_google.Empty:
        """Receive HA entity updates from integration"""
        logger.info("Starting to receive HA entity updates")

        async for entity_update in ha_entity_update_iterator:
            # Store the entity
            ha_entity = HAEntity(
                entity_id=entity_update.entity_id,
                domain=entity_update.domain,
                name=entity_update.name,
                state=entity_update.state,
                attributes=dict(entity_update.attributes),
                available=entity_update.available,
                last_updated=entity_update.last_updated,
            )

            self.ha_entities[entity_update.entity_id] = ha_entity
            logger.info(
                f"Received HA entity update: {entity_update.entity_id} ({entity_update.domain}) - {entity_update.state}"
            )

            # Update call stations when we get new camera or media_player entities
            await self._update_call_stations()

        return betterproto_lib_google.Empty()

    async def stream_broker_entities(
        self,
        betterproto_lib_pydantic_google_protobuf_empty: betterproto_lib_google.Empty,
    ) -> AsyncIterator[BrokerEntityUpdate]:
        """Stream broker entities to integration"""
        logger.info("Starting broker entity stream")

        # Create a queue for this subscriber
        update_queue = asyncio.Queue()
        self.broker_entity_subscribers.append(update_queue)

        try:
            # Send initial entities
            await self._send_initial_entities(update_queue)

            # Stream ongoing updates
            while True:
                try:
                    entity_update = await update_queue.get()
                    yield entity_update
                except asyncio.CancelledError:
                    break

        finally:
            # Clean up subscriber
            if update_queue in self.broker_entity_subscribers:
                self.broker_entity_subscribers.remove(update_queue)
            logger.info("Broker entity stream ended")

    async def health_check(
        self,
        betterproto_lib_pydantic_google_protobuf_empty: betterproto_lib_google.Empty,
    ) -> HealthCheckResponse:
        """Simple health check"""
        uptime = datetime.now(UTC) - self.startup_time

        return HealthCheckResponse(
            healthy=True,
            message=f"Broker running for {uptime.total_seconds():.0f} seconds",
            timestamp=datetime.now(UTC),
        )

    async def start_call(self, start_call_request: StartCallRequest) -> StartCallResponse:
        """Start a call using the specified call station and contact."""
        logger.info(f"Starting call from {start_call_request.call_station_id} to {start_call_request.contact}")

        # Validate call station exists
        if start_call_request.call_station_id not in self.call_stations:
            return StartCallResponse(
                success=False,
                message=f"Call station '{start_call_request.call_station_id}' not found",
                call_id="",
            )

        station = self.call_stations[start_call_request.call_station_id]

        # Check if call station is available
        if not station.available:
            return StartCallResponse(
                success=False,
                message=f"Call station '{start_call_request.call_station_id}' is not available",
                call_id="",
            )

        # Generate a unique call ID
        call_id = f"call_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{start_call_request.call_station_id}"

        try:
            # Update call station state
            station.state = "calling"

            # Notify subscribers of state change
            await self._notify_entity_changes()

            # Implement actual call logic via plugin manager
            success = await self._initiate_plugin_call(call_id, station, start_call_request.contact)

            if not success:
                station.state = "idle"  # Reset state on failure
                await self._notify_entity_changes()
                return StartCallResponse(
                    success=False,
                    message="Failed to initiate call through protocol plugins",
                    call_id="",
                )

            logger.info(f"Call {call_id} started successfully")

            return StartCallResponse(
                success=True,
                message=f"Call started successfully to {start_call_request.contact}",
                call_id=call_id,
            )

        except Exception as ex:
            logger.error(f"Failed to start call: {ex}")
            return StartCallResponse(
                success=False,
                message=f"Failed to start call: {str(ex)}",
                call_id="",
            )

    async def _update_call_stations(self):
        """Update call stations based on database configuration and HA entity availability"""
        if not self.database_manager:
            logger.warning("No database manager available, skipping call station update")
            return

        # Load call stations from database
        new_stations = {}
        with self.database_manager.get_session() as session:
            db_stations = get_enabled_call_stations_with_session(session)

            for db_station in db_stations:
                # Create in-memory CallStation object
                station = CallStation(
                    station_id=db_station.station_id,
                    name=db_station.display_name,
                    camera_entity_id=db_station.camera_entity_id,
                    media_player_entity_id=db_station.media_player_entity_id,
                )

                # Update availability based on both entities existing and being available
                camera_available = (
                    db_station.camera_entity_id in self.ha_entities and
                    self.ha_entities[db_station.camera_entity_id].available
                )
                player_available = (
                    db_station.media_player_entity_id in self.ha_entities and
                    self.ha_entities[db_station.media_player_entity_id].available
                )

                station.available = camera_available and player_available
                new_stations[db_station.station_id] = station


        # Check if stations changed
        if new_stations != self.call_stations:
            self.call_stations = new_stations
            logger.info(f"Updated call stations: {len(self.call_stations)} stations")

            # Notify subscribers of changes
            await self._notify_entity_changes()

    async def _send_initial_entities(self, update_queue: asyncio.Queue):
        """Send initial entities to a new subscriber"""
        # Send call stations
        for station in self.call_stations.values():
            entity_update = BrokerEntityUpdate(
                entity_id=station.station_id,
                name=station.name,
                entity_type=BrokerEntityType.CALL_STATION,
                state=station.state,
                attributes=station.attributes,
                icon="mdi:video-account",
                available=station.available,
                capabilities=["make_call"],
                last_updated=datetime.now(UTC),
            )
            await update_queue.put(entity_update)

        # Send broker status
        broker_status = BrokerEntityUpdate(
            entity_id="broker_status",
            name="Call Assist Broker",
            entity_type=BrokerEntityType.BROKER_STATUS,
            state="online",
            attributes={
                "monitored_cameras": str(
                    len([e for e in self.ha_entities.values() if e.domain == "camera"])
                ),
                "monitored_players": str(
                    len(
                        [
                            e
                            for e in self.ha_entities.values()
                            if e.domain == "media_player"
                        ]
                    )
                ),
                "call_stations": str(len(self.call_stations)),
                "uptime_seconds": str(
                    (datetime.now(UTC) - self.startup_time).total_seconds()
                ),
            },
            icon="mdi:video-switch",
            available=True,
            capabilities=[],
            last_updated=datetime.now(UTC),
        )
        await update_queue.put(broker_status)

    async def _notify_entity_changes(self):
        """Notify all subscribers of entity changes"""
        for update_queue in self.broker_entity_subscribers:
            try:
                # Send updated call stations
                for station in self.call_stations.values():
                    entity_update = BrokerEntityUpdate(
                        entity_id=station.station_id,
                        name=station.name,
                        entity_type=BrokerEntityType.CALL_STATION,
                        state=station.state,
                        attributes=station.attributes,
                        icon="mdi:video-account",
                        available=station.available,
                        capabilities=["make_call"],
                        last_updated=datetime.now(UTC),
                    )
                    await update_queue.put(entity_update)

            except asyncio.CancelledError:
                # Re-raise cancellation to propagate properly
                raise
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")
                # Continue with next subscriber

    async def _initiate_plugin_call(self, call_id: str, station, contact: str) -> bool:
        """Initiate a call through the appropriate protocol plugin"""
        try:
            # Determine protocol from contact format
            protocol = self._detect_protocol_from_contact(contact)
            if not protocol:
                logger.error(f"Could not determine protocol for contact: {contact}")
                return False

            # Get camera stream URL from HA entity attributes
            camera_entity = self.ha_entities.get(station.camera_entity_id)
            if not camera_entity:
                logger.error(f"Camera entity {station.camera_entity_id} not found")
                return False

            # Fix: ha_entities contains HAEntity objects, not dicts
            camera_stream_url = camera_entity.attributes.get("stream_source", "")
            if not camera_stream_url:
                logger.error(f"No stream source found for camera {station.camera_entity_id}")
                return False

            # Import CallStartRequest here to avoid circular imports
            from proto_gen.callassist.common import MediaCapabilities, Resolution
            from proto_gen.callassist.plugin import CallStartRequest

            # Create basic media capabilities using correct structure
            camera_capabilities = MediaCapabilities(
                video_codecs=["H264", "VP8"],
                audio_codecs=["OPUS", "PCMU"],
                supported_resolutions=[
                    Resolution(width=640, height=480, framerate=10),
                    Resolution(width=1280, height=720, framerate=30)
                ],
                hardware_acceleration=False,
                webrtc_support=True,
                max_bandwidth_kbps=2000
            )

            player_capabilities = MediaCapabilities(
                video_codecs=["H264", "VP8", "VP9"],
                audio_codecs=["OPUS", "AAC"],
                supported_resolutions=[
                    Resolution(width=1920, height=1080, framerate=30),
                    Resolution(width=1280, height=720, framerate=30)
                ],
                hardware_acceleration=True,
                webrtc_support=True,
                max_bandwidth_kbps=10000
            )

            # Create call start request
            call_request = CallStartRequest(
                call_id=call_id,
                target_address=contact,
                camera_stream_url=camera_stream_url,
                camera_capabilities=camera_capabilities,
                player_capabilities=player_capabilities,
            )

            # Call the plugin manager
            response = await self.plugin_manager.start_call(protocol, call_request)

            if response and response.success:
                logger.info(f"Plugin call started successfully: {response.message}")
                return True
            error_msg = response.message if response else "No response from plugin"
            logger.error(f"Plugin call failed: {error_msg}")
            return False

        except Exception as e:
            logger.error(f"Exception during plugin call initiation: {e}")
            return False

    def _detect_protocol_from_contact(self, contact: str) -> str:
        """Detect protocol from contact format"""
        if contact.startswith("@") and ":" in contact:
            return "matrix"  # Matrix user ID format: @user:server
        if "@" in contact and "." in contact:
            return "xmpp"    # XMPP JID format: user@domain
        return ""  # Unknown format


async def serve(
    grpc_host: str = "0.0.0.0",
    grpc_port: int = 50051,
    web_host: str = "0.0.0.0",
    web_port: int = 8080,
    db_path: str = "broker_data.db",
):
    """Start the consolidated Call Assist Broker with gRPC, web UI, and database"""
    logger.info(f"Initializing Call Assist Broker with database: {db_path}")

    # Initialize dependencies in correct order
    await app_state.initialize(db_path)

    # Create broker instance with injected dependencies
    broker = CallAssistBroker(
        plugin_manager=app_state.plugin_manager,
        database_manager=app_state.database_manager
    )
    app_state.set_broker_instance(broker)

    # Initialize web server
    web_server = WebUIServer()
    web_server.host = web_host
    web_server.port = web_port

    try:
        # Initialize gRPC server
        grpc_server = Server([broker])  # grpclib server

        logger.info("Starting Call Assist Broker:")
        logger.info(f"  - gRPC server: {grpc_host}:{grpc_port}")
        logger.info(f"  - Web UI: {web_host}:{web_port}")
        logger.info(f"  - Database: {db_path}")

        # Start gRPC server first (non-blocking)
        async def run_grpc_server():
            await grpc_server.start(grpc_host, grpc_port)
            logger.info(f"gRPC server listening on {grpc_host}:{grpc_port}")

            await grpc_server.wait_closed()

        grpc_task = asyncio.create_task(run_grpc_server())

        # Start web server in background (it runs forever)
        web_task = asyncio.create_task(web_server.start())
        logger.info(f"Web UI server starting on http://{web_host}:{web_port}")

        # Give web server a moment to start
        await asyncio.sleep(0.1)

        logger.info("Call Assist Broker fully operational")

        try:
            # Wait for termination signals
            await asyncio.gather(grpc_task, web_task)
        except asyncio.CancelledError:
            logger.info("Received cancellation signal, shutting down...")
            grpc_task.cancel()
            web_task.cancel()
            await asyncio.gather(grpc_task, web_task, return_exceptions=True)
        finally:
            logger.info("Shutting down servers...")
            grpc_server.close()
            await web_server.stop()
    finally:
        # Clean up all resources
        await app_state.cleanup()
        logger.info("Call Assist Broker shutdown complete")


async def main():
    """Main entry point with proper signal handling"""
    try:
        await serve()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Broker failed: {e}")
        raise


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Broker shutdown complete")
    except Exception as e:
        logger.error(f"Failed to start broker: {e}")
        raise
