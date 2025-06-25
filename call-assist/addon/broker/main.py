#!/usr/bin/env python3

import asyncio
import logging
import grpclib
from grpclib.server import Server
from typing import Dict, List, Optional, AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone

# Import betterproto generated classes
from proto_gen.callassist.broker import (
    BrokerIntegrationBase,
    HaEntityUpdate,
    BrokerEntityUpdate,
    BrokerEntityType,
    HealthCheckResponse,
    ProtocolSchemasResponse,
    ProtocolSchema,
    FieldDefinition,
)
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google
from addon.broker.database import set_database_path
from addon.broker.web_server import WebUIServer
from addon.broker.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


@dataclass
class HAEntity:
    """Represents a Home Assistant entity we're monitoring"""

    entity_id: str
    domain: str
    name: str
    state: str
    attributes: Dict[str, str]
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
    def attributes(self) -> Dict[str, str]:
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

    def __init__(self):
        # Store HA entities we receive
        self.ha_entities: Dict[str, HAEntity] = {}

        # Store call stations we create
        self.call_stations: Dict[str, CallStation] = {}

        # Track broker entity update subscribers
        self.broker_entity_subscribers: List[asyncio.Queue] = []

        # Startup time for health check
        self.startup_time = datetime.now(timezone.utc)
        
        # Initialize plugin manager
        self.plugin_manager = PluginManager()

    async def stream_ha_entities(
        self, ha_entity_update_iterator: AsyncIterator[HaEntityUpdate]
    ) -> betterproto_lib_google.Empty:
        """Receive HA entity updates from integration"""
        logger.info("Starting to receive HA entity updates")

        try:
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

        except Exception as e:
            logger.error(f"Error processing HA entity stream: {e}")

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

        except Exception as e:
            logger.error(f"Error in broker entity stream: {e}")
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
        uptime = datetime.now(timezone.utc) - self.startup_time

        return HealthCheckResponse(
            healthy=True,
            message=f"Broker running for {uptime.total_seconds():.0f} seconds",
            timestamp=datetime.now(timezone.utc),
        )

    async def get_protocol_schemas(
        self,
        betterproto_lib_pydantic_google_protobuf_empty: betterproto_lib_google.Empty,
    ) -> ProtocolSchemasResponse:
        """Get protocol schemas for UI generation"""
        schemas_dict = self.plugin_manager.get_protocol_schemas()
        schemas = []
        
        for protocol, schema_data in schemas_dict.items():
            # Convert credential fields
            credential_fields = [
                FieldDefinition(
                    key=field["key"],
                    display_name=field["display_name"],
                    description=field["description"],
                    type=field["type"],
                    required=field["required"],
                    default_value=field["default_value"],
                    sensitive=field["sensitive"],
                    allowed_values=field["allowed_values"],
                    placeholder=field["placeholder"],
                    validation_pattern=field["validation_pattern"]
                )
                for field in schema_data["credential_fields"]
            ]
            
            # Convert setting fields
            setting_fields = [
                FieldDefinition(
                    key=field["key"],
                    display_name=field["display_name"],
                    description=field["description"],
                    type=field["type"],
                    required=field["required"],
                    default_value=field["default_value"],
                    sensitive=field["sensitive"],
                    allowed_values=field["allowed_values"],
                    placeholder=field["placeholder"],
                    validation_pattern=field["validation_pattern"]
                )
                for field in schema_data["setting_fields"]
            ]
            
            schema = ProtocolSchema(
                protocol=protocol,
                display_name=schema_data["display_name"],
                description=schema_data["description"],
                credential_fields=credential_fields,
                setting_fields=setting_fields,
                example_account_ids=schema_data["example_account_ids"]
            )
            
            schemas.append(schema)
        
        return ProtocolSchemasResponse(schemas=schemas)

    async def _update_call_stations(self):
        """Update call stations based on available HA entities"""
        # Get cameras and media players
        cameras = {
            id: entity
            for id, entity in self.ha_entities.items()
            if entity.domain == "camera"
        }
        media_players = {
            id: entity
            for id, entity in self.ha_entities.items()
            if entity.domain == "media_player"
        }

        # Create call stations for each camera + media player combination
        new_stations = {}
        for camera_id, camera in cameras.items():
            for player_id, player in media_players.items():
                station_id = f"station_{camera_id}_{player_id}".replace(".", "_")

                # Create or update station
                if station_id in self.call_stations:
                    station = self.call_stations[station_id]
                else:
                    station = CallStation(
                        station_id=station_id,
                        name=f"{camera.name} + {player.name}",
                        camera_entity_id=camera_id,
                        media_player_entity_id=player_id,
                    )

                # Update availability based on both entities
                station.available = camera.available and player.available
                new_stations[station_id] = station

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
                last_updated=datetime.now(timezone.utc),
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
                    (datetime.now(timezone.utc) - self.startup_time).total_seconds()
                ),
            },
            icon="mdi:video-switch",
            available=True,
            capabilities=[],
            last_updated=datetime.now(timezone.utc),
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
                        last_updated=datetime.now(timezone.utc),
                    )
                    await update_queue.put(entity_update)

            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")


async def serve(
    grpc_host: str = "0.0.0.0",
    grpc_port: int = 50051,
    web_host: str = "0.0.0.0",
    web_port: int = 8080,
    db_path: str = "broker_data.db",
):
    """Start the consolidated Call Assist Broker with gRPC, web UI, and database"""
    logger.info(f"Initializing Call Assist Broker with database: {db_path}")

    # Set database path for lazy initialization
    set_database_path(db_path)

    # Create broker instance
    broker = CallAssistBroker()

    # Initialize web server
    web_server = WebUIServer(broker_ref=broker)
    web_server.host = web_host
    web_server.port = web_port

    try:
        # Initialize gRPC server
        grpc_server = Server([broker])  # grpclib server

        logger.info(f"Starting Call Assist Broker:")
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
        finally:
            logger.info("Shutting down servers...")
            grpc_server.close()
            await web_server.stop()
    finally:
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
