#!/usr/bin/env python3

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    import pychromecast  # type: ignore
    import pychromecast.controllers.media as media_controller  # type: ignore
    PYCHROMECAST_AVAILABLE = True
except ImportError:
    PYCHROMECAST_AVAILABLE = False
    pychromecast = None
    media_controller = None

from addon.broker.casting_service import (
    CastProvider,
    CastSession,
    CastState,
    CastTarget,
    CastTargetType,
)
from addon.broker.video_streaming_service import VideoFrame

logger = logging.getLogger(__name__)


class ChromecastProvider(CastProvider):
    """
    Chromecast casting provider using pychromecast library
    """

    def __init__(self) -> None:
        self.chromecasts: Dict[str, Any] = {}  # pychromecast.Chromecast
        self.active_sessions: Dict[str, CastSession] = {}
        self.media_controllers: Dict[str, Any] = {}  # media_controller.MediaController

    async def initialize(self) -> bool:
        """Initialize the Chromecast provider"""
        if not PYCHROMECAST_AVAILABLE:
            logger.error("pychromecast library not available. Install with: pip install pychromecast")
            return False

        logger.info("Chromecast provider initialized successfully")
        return True

    async def discover_targets(self) -> List[CastTarget]:
        """Discover available Chromecast devices"""
        if not PYCHROMECAST_AVAILABLE:
            return []

        targets = []
        
        try:
            # Run discovery in a thread to avoid blocking
            chromecasts, browser = await asyncio.get_event_loop().run_in_executor(
                None, pychromecast.get_chromecasts
            )
            
            for cast in chromecasts:
                target_id = f"chromecast_{cast.device.uuid}"
                
                target = CastTarget(
                    target_id=target_id,
                    name=cast.device.friendly_name,
                    target_type=CastTargetType.CHROMECAST,
                    connection_info={
                        "host": cast.host,
                        "port": str(cast.port),
                        "uuid": cast.device.uuid,
                        "model": cast.device.model_name,
                        "manufacturer": cast.device.manufacturer,
                    },
                )
                
                targets.append(target)
                self.chromecasts[target_id] = cast
                
                logger.info(f"Discovered Chromecast: {cast.device.friendly_name} ({cast.host})")

            # Stop the browser after discovery
            browser.stop_discovery()
            
        except Exception as e:
            logger.error(f"Error discovering Chromecast devices: {e}")

        return targets

    async def start_cast(self, target: CastTarget, call_id: str) -> Optional[str]:
        """Start casting to a Chromecast device"""
        if not PYCHROMECAST_AVAILABLE:
            return None

        if target.target_id not in self.chromecasts:
            logger.error(f"Chromecast {target.target_id} not found")
            return None

        cast = self.chromecasts[target.target_id]
        session_id = str(uuid4())

        try:
            # Wait for the device to be ready
            cast.wait()
            
            # Start the media controller
            mc = cast.media_controller
            self.media_controllers[session_id] = mc
            
            # Create session record
            session = CastSession(
                session_id=session_id,
                call_id=call_id,
                target=target,
                state=CastState.CONNECTING,
                started_at=datetime.now(UTC),
            )
            
            self.active_sessions[session_id] = session
            
            logger.info(f"Started Chromecast session {session_id} for {target.name}")
            return session_id
            
        except Exception as e:
            logger.error(f"Error starting Chromecast session: {e}")
            return None

    async def send_frame(self, session_id: str, frame: VideoFrame) -> bool:
        """
        Send a video frame to Chromecast
        
        Note: Chromecast doesn't support direct frame sending. In a real implementation,
        we would need to:
        1. Set up an HTTP server to serve the video stream
        2. Convert frames to a streamable format (HLS, DASH, or MP4)
        3. Tell Chromecast to play the stream URL
        
        For now, this is a placeholder that logs frame info.
        """
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]
        
        try:
            # TODO: Implement actual frame streaming to Chromecast
            # This would involve:
            # 1. Converting I420 frames to H.264 stream
            # 2. Serving the stream via HTTP
            # 3. Using cast.media_controller.play_media() with the stream URL
            
            # For now, just update session state
            session.last_frame_at = frame.timestamp
            session.frames_sent += 1
            session.state = CastState.STREAMING
            
            # Log occasionally
            if session.frames_sent % 100 == 0:
                logger.info(
                    f"[PLACEHOLDER] Would send frame {session.frames_sent} to Chromecast "
                    f"{session.target.name} ({frame.width}x{frame.height})"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending frame to Chromecast session {session_id}: {e}")
            session.state = CastState.ERROR
            session.error_message = str(e)
            return False

    async def stop_cast(self, session_id: str) -> bool:
        """Stop casting to Chromecast"""
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]
        
        try:
            # Stop media playback
            if session_id in self.media_controllers:
                mc = self.media_controllers[session_id]
                mc.stop()
                del self.media_controllers[session_id]
            
            # Update session state
            session.state = CastState.DISCONNECTED
            
            logger.info(f"Stopped Chromecast session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Chromecast session {session_id}: {e}")
            return False

    async def get_session_info(self, session_id: str) -> Optional[CastSession]:
        """Get information about a Chromecast session"""
        return self.active_sessions.get(session_id)

    async def cleanup(self) -> None:
        """Clean up Chromecast provider"""
        logger.info("Cleaning up Chromecast provider")
        
        # Stop all active sessions
        for session_id in list(self.active_sessions.keys()):
            await self.stop_cast(session_id)
        
        # Disconnect from all Chromecasts
        for cast in self.chromecasts.values():
            try:
                cast.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting from Chromecast: {e}")
        
        self.chromecasts.clear()
        self.active_sessions.clear()
        self.media_controllers.clear()
        
        logger.info("Chromecast provider cleanup completed")

    @property
    def target_type(self) -> CastTargetType:
        """Get the target type for this provider"""
        return CastTargetType.CHROMECAST

    @property
    def provider_name(self) -> str:
        """Get the name of this provider"""
        return "Chromecast Provider"