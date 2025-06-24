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
)
import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google

# Set up logging
logging.basicConfig(level=logging.INFO)
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

    async def stream_ha_entities(self, ha_entity_update_iterator: AsyncIterator[HaEntityUpdate]) -> betterproto_lib_google.Empty:
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
                logger.info(f"Received HA entity update: {entity_update.entity_id} ({entity_update.domain}) - {entity_update.state}")
                
                # Update call stations when we get new camera or media_player entities
                await self._update_call_stations()
                
        except Exception as e:
            logger.error(f"Error processing HA entity stream: {e}")
            
        return betterproto_lib_google.Empty()

    async def stream_broker_entities(self, betterproto_lib_pydantic_google_protobuf_empty: betterproto_lib_google.Empty) -> AsyncIterator[BrokerEntityUpdate]:
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

    async def health_check(self, betterproto_lib_pydantic_google_protobuf_empty: betterproto_lib_google.Empty) -> HealthCheckResponse:
        """Simple health check"""
        uptime = datetime.now(timezone.utc) - self.startup_time
        
        return HealthCheckResponse(
            healthy=True,
            message=f"Broker running for {uptime.total_seconds():.0f} seconds",
            timestamp=datetime.now(timezone.utc),
        )

    async def _update_call_stations(self):
        """Update call stations based on available HA entities"""
        # Get cameras and media players
        cameras = {id: entity for id, entity in self.ha_entities.items() if entity.domain == "camera"}
        media_players = {id: entity for id, entity in self.ha_entities.items() if entity.domain == "media_player"}
        
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
                "monitored_cameras": str(len([e for e in self.ha_entities.values() if e.domain == "camera"])),
                "monitored_players": str(len([e for e in self.ha_entities.values() if e.domain == "media_player"])),
                "call_stations": str(len(self.call_stations)),
                "uptime_seconds": str((datetime.now(timezone.utc) - self.startup_time).total_seconds()),
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
):
    """Start the simplified broker gRPC server"""
    broker = CallAssistBroker()

    try:
        # Initialize gRPC server
        server = Server([broker])  # grpclib server

        logger.info(f"Starting simplified Call Assist Broker on {grpc_host}:{grpc_port}")

        # Start gRPC server
        await server.start(grpc_host, grpc_port)
        logger.info(f"gRPC server started on {grpc_host}:{grpc_port}")

        try:
            # Wait for termination
            await server.wait_closed()
        finally:
            logger.info("Server shut down")

    except asyncio.CancelledError:
        logger.info("Received shutdown signal...")
    finally:
        logger.info("Shutting down broker...")


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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Broker shutdown complete")
    except Exception as e:
        logger.error(f"Failed to start broker: {e}")
        exit(1)