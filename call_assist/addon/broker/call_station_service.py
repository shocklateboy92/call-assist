#!/usr/bin/env python3
"""
Call Station service module for business logic related to call station management.

This module handles call station validation and other business logic,
using dependency injection for clean separation of concerns.
"""

import logging

from fastapi import Depends
from sqlmodel import Session

from call_assist.addon.broker.data_types import (
    AvailableEntitiesData,
    CallStationStatusData,
    EntityInfo,
    EntityOption,
    ValidationErrors,
)
from call_assist.addon.broker.dependencies import get_database_session
from call_assist.addon.broker.queries import get_all_call_stations_with_session

logger = logging.getLogger(__name__)


class CallStationService:
    """Call Station service with dependency injection"""

    def __init__(
        self,
        session: Session = Depends(get_database_session)
    ):
        self.session = session

    def get_call_stations_with_status(self, available_entities: dict[str, EntityInfo]) -> list[CallStationStatusData]:
        """Get all call stations with availability status based on HA entities"""
        call_stations = get_all_call_stations_with_session(self.session)
        stations_with_status = []

        for station in call_stations:
            # Check if both entities are available
            camera_available = (
                station.camera_entity_id in available_entities and
                available_entities[station.camera_entity_id].available
            )
            player_available = (
                station.media_player_entity_id in available_entities and
                available_entities[station.media_player_entity_id].available
            )

            # Get entity names for display
            if station.camera_entity_id in available_entities:
                camera_name = available_entities[station.camera_entity_id].name
            else:
                camera_name = f"{station.camera_entity_id} (not found)"

            if station.media_player_entity_id in available_entities:
                player_name = available_entities[station.media_player_entity_id].name
            else:
                player_name = f"{station.media_player_entity_id} (not found)"

            station_status = CallStationStatusData(
                id=station.id,
                station_id=station.station_id,
                display_name=station.display_name,
                camera_entity_id=station.camera_entity_id,
                media_player_entity_id=station.media_player_entity_id,
                enabled=station.enabled,
                created_at=station.created_at.strftime("%Y-%m-%d %H:%M:%S") if station.created_at else "",
                updated_at=station.updated_at.strftime("%Y-%m-%d %H:%M:%S") if station.updated_at else "",
                camera_available=camera_available,
                player_available=player_available,
                is_available=camera_available and player_available and station.enabled,
                camera_name=camera_name,
                player_name=player_name
            )
            stations_with_status.append(station_status)

        return stations_with_status

    def get_available_entities(self, ha_entities: dict[str, EntityInfo]) -> AvailableEntitiesData:
        """Get available camera and media player entities for form dropdowns"""
        cameras = []
        media_players = []

        for entity_id, entity in ha_entities.items():
            if entity.domain == "camera":
                cameras.append(EntityOption(
                    entity_id=entity_id,
                    name=entity.name
                ))
            elif entity.domain == "media_player":
                media_players.append(EntityOption(
                    entity_id=entity_id,
                    name=entity.name
                ))

        return AvailableEntitiesData(
            cameras=sorted(cameras, key=lambda x: x.name),
            media_players=sorted(media_players, key=lambda x: x.name)
        )

    def validate_call_station_entities(self, camera_entity_id: str, media_player_entity_id: str, ha_entities: dict[str, EntityInfo]) -> ValidationErrors:
        """Validate that the specified entities exist and are of correct types"""
        camera_error = None
        player_error = None

        # Check camera entity
        if camera_entity_id not in ha_entities:
            camera_error = "Camera entity not found"
        elif ha_entities[camera_entity_id].domain != "camera":
            camera_error = "Entity is not a camera"

        # Check media player entity
        if media_player_entity_id not in ha_entities:
            player_error = "Media player entity not found"
        elif ha_entities[media_player_entity_id].domain != "media_player":
            player_error = "Entity is not a media player"

        return ValidationErrors(
            camera_entity_id=camera_error,
            media_player_entity_id=player_error
        )


# Dependency injection helper functions for FastAPI routes
async def get_call_station_service(
    session: Session = Depends(get_database_session)
) -> CallStationService:
    """Get CallStationService with injected dependencies"""
    return CallStationService(session)


# Use dependency injection via get_call_station_service() for FastAPI routes
