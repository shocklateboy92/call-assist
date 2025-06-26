#!/usr/bin/env python3
"""
Call Station service module for business logic related to call station management.

This module handles call station validation and other business logic,
using dependency injection for clean separation of concerns.
"""

import logging
from typing import Dict, Any, List, Set
from fastapi import Depends
from sqlmodel import Session

from addon.broker.dependencies import get_database_session
from addon.broker.queries import get_all_call_stations_with_session
from addon.broker.models import CallStation

logger = logging.getLogger(__name__)


class CallStationService:
    """Call Station service with dependency injection"""
    
    def __init__(
        self,
        session: Session = Depends(get_database_session)
    ):
        self.session = session

    def get_call_stations_with_status(self, available_entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get all call stations with availability status based on HA entities"""
        call_stations = get_all_call_stations_with_session(self.session)
        stations_with_status = []
        
        for station in call_stations:
            station_dict = {
                "id": station.id,
                "station_id": station.station_id,
                "display_name": station.display_name,
                "camera_entity_id": station.camera_entity_id,
                "media_player_entity_id": station.media_player_entity_id,
                "enabled": station.enabled,
                "created_at": station.created_at.strftime("%Y-%m-%d %H:%M:%S") if station.created_at else "",
                "updated_at": station.updated_at.strftime("%Y-%m-%d %H:%M:%S") if station.updated_at else "",
            }
            
            # Check if both entities are available
            camera_available = (
                station.camera_entity_id in available_entities and
                available_entities[station.camera_entity_id].get("available", False)
            )
            player_available = (
                station.media_player_entity_id in available_entities and
                available_entities[station.media_player_entity_id].get("available", False)
            )
            
            station_dict["camera_available"] = camera_available
            station_dict["player_available"] = player_available
            station_dict["is_available"] = camera_available and player_available and station.enabled
            
            # Add entity names for display
            if station.camera_entity_id in available_entities:
                station_dict["camera_name"] = available_entities[station.camera_entity_id].get("name", station.camera_entity_id)
            else:
                station_dict["camera_name"] = f"{station.camera_entity_id} (not found)"
                
            if station.media_player_entity_id in available_entities:
                station_dict["player_name"] = available_entities[station.media_player_entity_id].get("name", station.media_player_entity_id)
            else:
                station_dict["player_name"] = f"{station.media_player_entity_id} (not found)"
            
            stations_with_status.append(station_dict)
        
        return stations_with_status

    def get_available_entities(self, ha_entities: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
        """Get available camera and media player entities for form dropdowns"""
        cameras = []
        media_players = []
        
        for entity_id, entity in ha_entities.items():
            if entity.domain == "camera":
                cameras.append({
                    "entity_id": entity_id,
                    "name": entity.name
                })
            elif entity.domain == "media_player":
                media_players.append({
                    "entity_id": entity_id,
                    "name": entity.name
                })
        
        return {
            "cameras": sorted(cameras, key=lambda x: x["name"]),
            "media_players": sorted(media_players, key=lambda x: x["name"])
        }

    def validate_call_station_entities(self, camera_entity_id: str, media_player_entity_id: str, ha_entities: Dict[str, Any]) -> Dict[str, str]:
        """Validate that the specified entities exist and are of correct types"""
        errors = {}
        
        # Check camera entity
        if camera_entity_id not in ha_entities:
            errors["camera_entity_id"] = "Camera entity not found"
        elif ha_entities[camera_entity_id].domain != "camera":
            errors["camera_entity_id"] = "Entity is not a camera"
        
        # Check media player entity
        if media_player_entity_id not in ha_entities:
            errors["media_player_entity_id"] = "Media player entity not found"
        elif ha_entities[media_player_entity_id].domain != "media_player":
            errors["media_player_entity_id"] = "Entity is not a media player"
        
        return errors


# Dependency injection helper functions for FastAPI routes
async def get_call_station_service(
    session: Session = Depends(get_database_session)
) -> CallStationService:
    """Get CallStationService with injected dependencies"""
    return CallStationService(session)


# Use dependency injection via get_call_station_service() for FastAPI routes
