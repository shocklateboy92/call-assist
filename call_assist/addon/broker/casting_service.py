#!/usr/bin/env python3

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Dict, List, Optional, Protocol

from addon.broker.video_streaming_service import VideoFrame, VideoStreamingService

logger = logging.getLogger(__name__)


class CastTargetType(Enum):
    """Types of casting targets"""

    CHROMECAST = "chromecast"
    HOME_ASSISTANT_MEDIA_PLAYER = "home_assistant_media_player"
    F_CAST = "f_cast"
    MIRACAST = "miracast"
    CUSTOM = "custom"


class CastState(Enum):
    """States of a casting session"""

    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class CastTarget:
    """Configuration for a casting target"""

    target_id: str
    name: str
    target_type: CastTargetType
    connection_info: Dict[str, str]  # Provider-specific connection details
    enabled: bool = True


@dataclass
class CastSession:
    """Information about an active casting session"""

    session_id: str
    call_id: str
    target: CastTarget
    state: CastState
    started_at: datetime
    last_frame_at: Optional[datetime] = None
    frames_sent: int = 0
    error_message: Optional[str] = None


class CastProvider(ABC):
    """Abstract base class for casting providers"""

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the provider. Returns True if successful."""
        pass

    @abstractmethod
    async def discover_targets(self) -> List[CastTarget]:
        """Discover available casting targets. Returns list of targets."""
        pass

    @abstractmethod
    async def start_cast(self, target: CastTarget, call_id: str) -> Optional[str]:
        """Start casting to target. Returns session_id if successful, None if failed."""
        pass

    @abstractmethod
    async def send_frame(self, session_id: str, frame: VideoFrame) -> bool:
        """Send a video frame to the casting target. Returns True if successful."""
        pass

    @abstractmethod
    async def stop_cast(self, session_id: str) -> bool:
        """Stop casting session. Returns True if successful."""
        pass

    @abstractmethod
    async def get_session_info(self, session_id: str) -> Optional[CastSession]:
        """Get information about a casting session."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up provider resources."""
        pass

    @property
    @abstractmethod
    def target_type(self) -> CastTargetType:
        """Get the type of targets this provider handles."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the name of this provider."""
        pass


class CastingService:
    """
    Main casting service that manages multiple providers and coordinates video streaming
    """

    def __init__(self, video_service: VideoStreamingService):
        self.video_service = video_service
        self.providers: Dict[CastTargetType, CastProvider] = {}
        self.active_sessions: Dict[str, CastSession] = {}
        self.target_registry: Dict[str, CastTarget] = {}
        self.frame_queue: Optional[asyncio.Queue[VideoFrame]] = None
        self._frame_processor_task: Optional[asyncio.Task[None]] = None
        self._discovery_task: Optional[asyncio.Task[None]] = None

    async def initialize(self) -> None:
        """Initialize the casting service"""
        logger.info("Initializing casting service")

        # Initialize all registered providers
        for provider_type, provider in self.providers.items():
            try:
                success = await provider.initialize()
                if success:
                    logger.info(
                        f"Provider {provider.provider_name} initialized successfully"
                    )
                else:
                    logger.error(
                        f"Failed to initialize provider {provider.provider_name}"
                    )
            except Exception as e:
                logger.error(
                    f"Error initializing provider {provider.provider_name}: {e}"
                )

        # Subscribe to video frames
        self.frame_queue = self.video_service.subscribe_to_frames()

        # Start frame processing task
        self._frame_processor_task = asyncio.create_task(self._process_frames())

        # Start target discovery task
        self._discovery_task = asyncio.create_task(
            self._discover_targets_periodically()
        )

        logger.info("Casting service initialized successfully")

    def register_provider(self, provider: CastProvider) -> None:
        """Register a casting provider"""
        self.providers[provider.target_type] = provider
        logger.info(
            f"Registered casting provider: {provider.provider_name} ({provider.target_type.value})"
        )

    async def discover_targets(self) -> List[CastTarget]:
        """Discover all available casting targets"""
        all_targets = []

        for provider in self.providers.values():
            try:
                targets = await provider.discover_targets()
                all_targets.extend(targets)
                logger.info(
                    f"Discovered {len(targets)} targets from {provider.provider_name}"
                )
            except Exception as e:
                logger.error(
                    f"Error discovering targets from {provider.provider_name}: {e}"
                )

        # Update target registry
        for target in all_targets:
            self.target_registry[target.target_id] = target

        return all_targets

    async def start_cast(self, target_id: str, call_id: str) -> Optional[str]:
        """Start casting a call to a target"""
        if target_id not in self.target_registry:
            logger.error(f"Cast target {target_id} not found")
            return None

        target = self.target_registry[target_id]

        if target.target_type not in self.providers:
            logger.error(
                f"No provider available for target type {target.target_type.value}"
            )
            return None

        provider = self.providers[target.target_type]

        try:
            session_id = await provider.start_cast(target, call_id)
            if session_id:
                # Create session record
                session = CastSession(
                    session_id=session_id,
                    call_id=call_id,
                    target=target,
                    state=CastState.CONNECTING,
                    started_at=datetime.now(UTC),
                )
                self.active_sessions[session_id] = session

                logger.info(
                    f"Started casting session {session_id} for call {call_id} to {target.name}"
                )
                return session_id
            else:
                logger.error(f"Failed to start casting to {target.name}")
                return None

        except Exception as e:
            logger.error(f"Error starting cast to {target.name}: {e}")
            return None

    async def stop_cast(self, session_id: str) -> bool:
        """Stop a casting session"""
        if session_id not in self.active_sessions:
            logger.warning(f"Casting session {session_id} not found")
            return False

        session = self.active_sessions[session_id]
        provider = self.providers.get(session.target.target_type)

        if not provider:
            logger.error(f"No provider for session {session_id}")
            return False

        try:
            success = await provider.stop_cast(session_id)
            if success:
                session.state = CastState.DISCONNECTED
                logger.info(f"Stopped casting session {session_id}")
            else:
                logger.error(f"Failed to stop casting session {session_id}")

            # Remove from active sessions
            del self.active_sessions[session_id]
            return success

        except Exception as e:
            logger.error(f"Error stopping cast session {session_id}: {e}")
            return False

    async def get_active_sessions(self) -> List[CastSession]:
        """Get list of active casting sessions"""
        return list(self.active_sessions.values())

    async def get_session_info(self, session_id: str) -> Optional[CastSession]:
        """Get information about a specific casting session"""
        return self.active_sessions.get(session_id)

    async def _process_frames(self) -> None:
        """Process incoming video frames and send to active casting sessions"""
        if not self.frame_queue:
            return

        logger.info("Started video frame processing for casting")

        while True:
            try:
                # Get frame from queue
                frame = await self.frame_queue.get()

                # Send frame to all active sessions for this call
                for session in self.active_sessions.values():
                    if (
                        session.call_id == frame.call_id
                        and session.state == CastState.STREAMING
                    ):
                        await self._send_frame_to_session(session, frame)

            except asyncio.CancelledError:
                logger.info("Frame processing task cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing video frame: {e}")
                await asyncio.sleep(1)  # Brief pause before retrying

    async def _send_frame_to_session(
        self, session: CastSession, frame: VideoFrame
    ) -> None:
        """Send a frame to a specific casting session"""
        provider = self.providers.get(session.target.target_type)
        if not provider:
            return

        try:
            success = await provider.send_frame(session.session_id, frame)
            if success:
                session.last_frame_at = frame.timestamp
                session.frames_sent += 1
                session.state = CastState.STREAMING

                # Log occasionally to avoid spam
                if session.frames_sent % 100 == 0:
                    logger.info(
                        f"Sent {session.frames_sent} frames to session {session.session_id}"
                    )
            else:
                logger.warning(f"Failed to send frame to session {session.session_id}")
                session.state = CastState.ERROR
                session.error_message = "Frame transmission failed"

        except Exception as e:
            logger.error(f"Error sending frame to session {session.session_id}: {e}")
            session.state = CastState.ERROR
            session.error_message = str(e)

    async def _discover_targets_periodically(self) -> None:
        """Periodically discover new casting targets"""
        while True:
            try:
                await self.discover_targets()
                await asyncio.sleep(60)  # Discover every minute
            except asyncio.CancelledError:
                logger.info("Target discovery task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in target discovery: {e}")
                await asyncio.sleep(10)  # Wait before retrying

    async def cleanup(self) -> None:
        """Clean up the casting service"""
        logger.info("Cleaning up casting service")

        # Cancel background tasks
        if self._frame_processor_task:
            self._frame_processor_task.cancel()
            try:
                await self._frame_processor_task
            except asyncio.CancelledError:
                pass

        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass

        # Stop all active casting sessions
        for session_id in list(self.active_sessions.keys()):
            await self.stop_cast(session_id)

        # Clean up providers
        for provider in self.providers.values():
            try:
                await provider.cleanup()
            except Exception as e:
                logger.error(
                    f"Error cleaning up provider {provider.provider_name}: {e}"
                )

        # Unsubscribe from video frames
        if self.frame_queue:
            self.video_service.unsubscribe_from_frames(self.frame_queue)

        logger.info("Casting service cleanup completed")
