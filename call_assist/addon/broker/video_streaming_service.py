#!/usr/bin/env python3

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Dict, List, Optional

import betterproto.lib.pydantic.google.protobuf as betterproto_lib_google

from proto_gen.callassist.plugin import (
    CallPluginBase,
    RemoteVideoFrame,
    RemoteVideoStreamInfo,
    TrackInfo,
    TrackKind,
)

logger = logging.getLogger(__name__)


@dataclass
class VideoStreamInfo:
    """Information about an active video stream"""
    call_id: str
    stream_id: str
    tracks: List[TrackInfo]
    started_at: datetime
    last_frame_at: Optional[datetime] = None
    frame_count: int = 0


@dataclass
class VideoFrame:
    """A video frame with metadata"""
    call_id: str
    stream_id: str
    timestamp: datetime
    width: int
    height: int
    format: str
    frame_data: bytes
    rotation: int


@dataclass
class StreamStats:
    """Statistics for a single video stream"""
    frame_count: int
    started_at: str
    last_frame_at: Optional[str]


@dataclass
class VideoStreamingStats:
    """Overall video streaming statistics"""
    active_streams: int
    total_stored_frames: int
    frame_subscribers: int
    streams: Dict[str, StreamStats]


class VideoStreamingService(CallPluginBase):
    """
    Service to handle incoming video streams from call plugins.
    
    This service implements the CallPlugin interface to receive video
    frames from plugins like the Matrix plugin.
    """

    def __init__(self) -> None:
        self.active_streams: Dict[str, VideoStreamInfo] = {}
        self.recent_frames: Dict[str, List[VideoFrame]] = {}  # Store recent frames for casting
        self.frame_subscribers: List[asyncio.Queue[VideoFrame]] = []
        
        # Configuration for frame storage
        self.max_frames_per_stream = 10  # Keep last 10 frames for each stream
        self.stream_timeout_seconds = 30  # Clean up streams after 30s of inactivity

    async def stream_remote_video(
        self, remote_video_frame_iterator: AsyncIterator[RemoteVideoFrame]
    ) -> betterproto_lib_google.Empty:
        """Receive video frames from plugins"""
        logger.info("Started receiving remote video stream from plugin")

        try:
            async for frame_msg in remote_video_frame_iterator:
                await self._handle_video_frame(frame_msg)
        except Exception as e:
            logger.error(f"Error in video stream: {e}")
        finally:
            logger.info("Remote video stream ended")

        return betterproto_lib_google.Empty()

    async def _handle_video_frame(self, frame_msg: RemoteVideoFrame) -> None:
        """Process a received video frame"""
        try:
            # Convert protobuf message to internal format
            frame = VideoFrame(
                call_id=frame_msg.call_id,
                stream_id=frame_msg.stream_id,
                timestamp=frame_msg.timestamp,
                width=frame_msg.width,
                height=frame_msg.height,
                format=frame_msg.format,
                frame_data=bytes(frame_msg.frame_data),
                rotation=frame_msg.rotation,
            )

            # Update stream info
            await self._update_stream_info(frame)

            # Store frame for casting services
            await self._store_frame(frame)

            # Notify frame subscribers (casting services)
            await self._notify_frame_subscribers(frame)

            # Log occasionally to avoid spam
            if frame.call_id in self.active_streams:
                stream_info = self.active_streams[frame.call_id]
                if stream_info.frame_count % 100 == 0:  # Log every 100 frames
                    logger.info(
                        f"Processed {stream_info.frame_count} frames for call {frame.call_id} "
                        f"({frame.width}x{frame.height}, {frame.format})"
                    )

        except Exception as e:
            logger.error(f"Error handling video frame for call {frame_msg.call_id}: {e}")

    async def _update_stream_info(self, frame: VideoFrame) -> None:
        """Update stream information"""
        if frame.call_id not in self.active_streams:
            # New stream
            self.active_streams[frame.call_id] = VideoStreamInfo(
                call_id=frame.call_id,
                stream_id=frame.stream_id,
                tracks=[],  # Will be populated by stream info messages
                started_at=datetime.now(UTC),
                last_frame_at=frame.timestamp,
                frame_count=1,
            )
            logger.info(f"Started tracking video stream for call {frame.call_id}")
        else:
            # Update existing stream
            stream_info = self.active_streams[frame.call_id]
            stream_info.last_frame_at = frame.timestamp
            stream_info.frame_count += 1

    async def _store_frame(self, frame: VideoFrame) -> None:
        """Store frame for casting services"""
        if frame.call_id not in self.recent_frames:
            self.recent_frames[frame.call_id] = []

        frames_list = self.recent_frames[frame.call_id]
        frames_list.append(frame)

        # Keep only recent frames
        if len(frames_list) > self.max_frames_per_stream:
            frames_list.pop(0)

    async def _notify_frame_subscribers(self, frame: VideoFrame) -> None:
        """Notify casting services of new frames"""
        for queue in self.frame_subscribers:
            try:
                # Non-blocking put - if queue is full, skip this subscriber
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                logger.warning(f"Frame subscriber queue full, dropping frame for call {frame.call_id}")
            except Exception as e:
                logger.error(f"Error notifying frame subscriber: {e}")

    def subscribe_to_frames(self) -> asyncio.Queue[VideoFrame]:
        """Subscribe to receive video frames (for casting services)"""
        queue: asyncio.Queue[VideoFrame] = asyncio.Queue(maxsize=50)
        self.frame_subscribers.append(queue)
        logger.info("New frame subscriber added")
        return queue

    def unsubscribe_from_frames(self, queue: asyncio.Queue[VideoFrame]) -> None:
        """Unsubscribe from video frames"""
        if queue in self.frame_subscribers:
            self.frame_subscribers.remove(queue)
            logger.info("Frame subscriber removed")

    def get_active_streams(self) -> Dict[str, VideoStreamInfo]:
        """Get information about active video streams"""
        return self.active_streams.copy()

    def get_recent_frames(self, call_id: str, count: int = 5) -> List[VideoFrame]:
        """Get recent frames for a specific call"""
        if call_id not in self.recent_frames:
            return []
        
        frames = self.recent_frames[call_id]
        return frames[-count:] if len(frames) > count else frames

    async def cleanup_inactive_streams(self) -> None:
        """Clean up streams that haven't received frames recently"""
        current_time = datetime.now(UTC)
        inactive_calls = []

        for call_id, stream_info in self.active_streams.items():
            if stream_info.last_frame_at:
                time_since_last_frame = (current_time - stream_info.last_frame_at).total_seconds()
                if time_since_last_frame > self.stream_timeout_seconds:
                    inactive_calls.append(call_id)

        for call_id in inactive_calls:
            logger.info(f"Cleaning up inactive video stream for call {call_id}")
            del self.active_streams[call_id]
            if call_id in self.recent_frames:
                del self.recent_frames[call_id]

    async def start_cleanup_task(self) -> None:
        """Start background task to clean up inactive streams"""
        async def cleanup_loop() -> None:
            while True:
                try:
                    await self.cleanup_inactive_streams()
                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
                    await asyncio.sleep(10)  # Wait before retrying

        asyncio.create_task(cleanup_loop())
        logger.info("Started video stream cleanup task")

    def get_stream_stats(self) -> VideoStreamingStats:
        """Get statistics about video streaming"""
        total_frames = sum(len(frames) for frames in self.recent_frames.values())
        
        streams_stats = {}
        for call_id, info in self.active_streams.items():
            streams_stats[call_id] = StreamStats(
                frame_count=info.frame_count,
                started_at=info.started_at.isoformat(),
                last_frame_at=info.last_frame_at.isoformat() if info.last_frame_at else None,
            )
        
        return VideoStreamingStats(
            active_streams=len(self.active_streams),
            total_stored_frames=total_frames,
            frame_subscribers=len(self.frame_subscribers),
            streams=streams_stats,
        )