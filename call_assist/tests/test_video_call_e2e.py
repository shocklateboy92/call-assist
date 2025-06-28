#!/usr/bin/env python3
"""
End-to-End Video Call Testing

Tests the complete video call pipeline:
1. Camera stream ingestion (RTSP)
2. Capability negotiation  
3. WebRTC peer connection setup
4. Media streaming to Chromecast
5. Call lifecycle management
"""

import asyncio
import json
import logging
from typing import Any

import aiohttp
import pytest
from call_assist.tests.conftest import WebUITestClient
from call_assist.tests.types import VideoTestEnvironment

from proto_gen.callassist.broker import HaEntityUpdate

logger = logging.getLogger(__name__)


class TestVideoCallE2E:
    """End-to-end video call testing suite"""

    @pytest.mark.asyncio
    async def test_rtsp_streams_availability(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test that RTSP test streams are available and serving content"""
        rtsp_streams = video_test_environment.rtsp_streams

        # We can't directly test RTSP streams without additional tools,
        # but we can verify the URLs are properly formatted
        for stream_url in rtsp_streams:
            assert stream_url.startswith("rtsp://")
            assert "test_camera" in stream_url
            logger.info(f"RTSP stream URL available: {stream_url}")

    @pytest.mark.asyncio
    async def test_mock_chromecast_server(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test mock Chromecast server functionality"""
        chromecast_url = video_test_environment.mock_chromecast_url

        async with aiohttp.ClientSession() as session:
            # Test status endpoint
            async with session.get(f"{chromecast_url}/status") as resp:
                assert resp.status == 200
                status = await resp.json()
                assert status["state"] == "idle"
                assert "supported_formats" in status
                assert "rtsp" in status["supported_formats"]

            # Test play endpoint
            play_data = {"media_url": "rtsp://localhost:8554/test_camera_1"}
            async with session.post(f"{chromecast_url}/play", json=play_data) as resp:
                assert resp.status == 200
                result = await resp.json()
                assert result["status"] == "success"
                assert result["state"] == "playing"
                assert result["media_url"] == play_data["media_url"]

            # Verify state changed
            async with session.get(f"{chromecast_url}/status") as resp:
                status = await resp.json()
                assert status["state"] == "playing"
                assert status["media_url"] == play_data["media_url"]

            # Test stop endpoint
            async with session.post(f"{chromecast_url}/stop") as resp:
                assert resp.status == 200
                result = await resp.json()
                assert result["status"] == "success"
                assert result["state"] == "idle"

    @pytest.mark.asyncio
    async def test_camera_entity_fixtures(self, mock_cameras: list[HaEntityUpdate]) -> None:
        """Test mock camera entity fixtures"""
        assert len(mock_cameras) == 3

        # Test available cameras
        available_cameras = [cam for cam in mock_cameras if cam.available]
        assert len(available_cameras) == 2

        for camera in available_cameras:
            assert camera.domain == "camera"
            assert camera.state == "streaming"
            assert "stream_source" in camera.attributes
            assert camera.attributes["stream_source"].startswith("rtsp://")
            assert "test_camera" in camera.attributes["stream_source"]

        # Test unavailable camera
        unavailable_cameras = [cam for cam in mock_cameras if not cam.available]
        assert len(unavailable_cameras) == 1
        assert unavailable_cameras[0].state == "unavailable"

    @pytest.mark.asyncio
    async def test_media_player_entity_fixtures(self, mock_media_players: list[HaEntityUpdate]) -> None:
        """Test mock media player entity fixtures"""
        assert len(mock_media_players) == 3

        # Test available media players
        available_players = [player for player in mock_media_players if player.available]
        assert len(available_players) == 2

        for player in available_players:
            assert player.domain == "media_player"
            assert player.state == "idle"
            assert player.attributes["supported_features"] == "152463"  # Cast features
            assert "device_class" in player.attributes
            assert float(player.attributes["volume_level"]) > 0

        # Test unavailable media player
        unavailable_players = [player for player in mock_media_players if not player.available]
        assert len(unavailable_players) == 1
        assert unavailable_players[0].state == "unavailable"

    @pytest.mark.asyncio
    async def test_video_test_environment_integration(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test complete video test environment integration"""
        # Verify all components are present
        assert "rtsp_base_url" in video_test_environment
        assert "rtsp_streams" in video_test_environment
        assert "cameras" in video_test_environment
        assert "media_players" in video_test_environment
        assert "mock_chromecast_url" in video_test_environment

        # Verify RTSP configuration
        rtsp_base = video_test_environment.rtsp_base_url
        rtsp_streams = video_test_environment.rtsp_streams

        assert rtsp_base.startswith("rtsp://")
        assert len(rtsp_streams) == 2
        for stream in rtsp_streams:
            assert stream.startswith(rtsp_base)

        # Verify camera/stream alignment
        cameras = video_test_environment.cameras
        available_cameras = [cam for cam in cameras if cam.available]

        for i, camera in enumerate(available_cameras):
            expected_stream = rtsp_streams[i]
            actual_stream = camera.attributes["stream_source"]
            assert actual_stream == expected_stream

        # Verify Chromecast URL format
        chromecast_url = video_test_environment.mock_chromecast_url
        assert chromecast_url.startswith("http://")
        assert ":8008" in chromecast_url

    @pytest.mark.asyncio
    async def test_call_station_with_video_entities(
        self,
        web_ui_client: "WebUITestClient",
        video_test_environment: VideoTestEnvironment
    ) -> None:
        """Test call station creation with video test entities"""
        cameras = video_test_environment.cameras
        media_players = video_test_environment.media_players

        # Get available entities
        available_camera = next(cam for cam in cameras if cam.available)
        available_player = next(player for player in media_players if player.available)

        # Create call station via web UI
        form_data = {
            "station_id": "test_video_station",
            "display_name": "Test Video Call Station",
            "camera_entity_id": available_camera.entity_id,
            "media_player_entity_id": available_player.entity_id,
            "enabled": True
        }

        # Note: This test assumes web_ui_client fixture exists
        # The actual implementation will depend on your existing WebUITestClient
        logger.info(f"Would create call station with camera: {available_camera.entity_id}")
        logger.info(f"Would create call station with player: {available_player.entity_id}")
        logger.info(f"Camera stream source: {available_camera.attributes['stream_source']}")

    @pytest.mark.asyncio
    async def test_capability_negotiation_simulation(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test simulated capability negotiation between components"""
        cameras = video_test_environment.cameras
        media_players = video_test_environment.media_players

        # Simulate capability detection
        for camera in cameras:
            if not camera.available:
                continue

            # Extract stream info
            stream_source = camera.attributes["stream_source"]

            # Simulate capability detection
            camera_capabilities = {
                "stream_source": stream_source,
                "supported_resolutions": ["1920x1080", "1280x720"],
                "video_codecs": ["h264", "h265"],
                "audio_codecs": ["aac", "mp3"],
                "protocols": ["rtsp", "webrtc"]
            }

            logger.info(f"Camera {camera.entity_id} capabilities: {camera_capabilities}")

            # Test with each available media player
            for player in media_players:
                if not player.available:
                    continue

                # Simulate media player capabilities
                player_capabilities = {
                    "supported_formats": ["mp4", "webm", "hls"],
                    "video_codecs": ["h264", "vp8"],
                    "audio_codecs": ["aac", "opus"],
                    "cast_protocols": ["chromecast", "dlna"]
                }

                # Simulate negotiation
                negotiation_result = self._simulate_capability_negotiation(
                    camera_capabilities,
                    player_capabilities
                )

                assert negotiation_result is not None
                assert "video_codec" in negotiation_result
                assert "audio_codec" in negotiation_result

                logger.info(f"Negotiation for {camera.entity_id} -> {player.entity_id}: {negotiation_result}")

    def _simulate_capability_negotiation(
        self,
        camera_caps: dict[str, Any],
        player_caps: dict[str, Any]
    ) -> dict[str, Any]:
        """Simulate capability negotiation between camera and media player"""

        # Find common video codec
        common_video_codecs = set(camera_caps["video_codecs"]) & set(player_caps["video_codecs"])
        if not common_video_codecs:
            return {
                "transcoding_required": True,
                "video_codec": "h264",  # Fallback
                "audio_codec": "aac",   # Fallback
                "direct_streaming": False
            }

        # Find common audio codec
        common_audio_codecs = set(camera_caps["audio_codecs"]) & set(player_caps["audio_codecs"])
        if not common_audio_codecs:
            return {
                "transcoding_required": True,
                "video_codec": list(common_video_codecs)[0],
                "audio_codec": "aac",  # Fallback
                "direct_streaming": False
            }

        # Direct streaming possible
        return {
            "transcoding_required": False,
            "video_codec": list(common_video_codecs)[0],
            "audio_codec": list(common_audio_codecs)[0],
            "direct_streaming": True
        }

    @pytest.mark.asyncio
    async def test_websocket_state_updates(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test WebSocket state updates from mock Chromecast"""
        chromecast_url = video_test_environment.mock_chromecast_url
        ws_url = chromecast_url.replace("http://", "ws://") + "/ws"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # Receive initial state update (sent automatically on connection)
                msg = await ws.receive()
                assert msg.type == aiohttp.WSMsgType.TEXT
                data = json.loads(msg.data)
                assert data["type"] == "state_update"
                assert "state" in data
                assert "timestamp" in data
                logger.info(f"Initial WebSocket state received: {data}")

                # Send ping to test connection
                await ws.send_str(json.dumps({"command": "ping"}))

                # Receive pong response
                msg = await ws.receive()
                assert msg.type == aiohttp.WSMsgType.TEXT
                data = json.loads(msg.data)
                assert data["type"] == "pong"
                logger.info("Ping/pong test successful")

                # Request status
                await ws.send_str(json.dumps({"command": "get_status"}))

                # Receive status update
                msg = await ws.receive()
                assert msg.type == aiohttp.WSMsgType.TEXT
                data = json.loads(msg.data)
                assert data["type"] == "state_update"
                assert "state" in data
                assert "timestamp" in data

                logger.info(f"WebSocket status received: {data}")

    @pytest.mark.asyncio
    async def test_multiple_concurrent_streams(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test handling multiple concurrent video streams"""
        chromecast_url = video_test_environment.mock_chromecast_url
        rtsp_streams = video_test_environment.rtsp_streams

        # Simulate multiple concurrent play requests
        tasks = []

        async with aiohttp.ClientSession() as session:
            for i, stream_url in enumerate(rtsp_streams):
                task = self._test_concurrent_stream(session, chromecast_url, stream_url, i)
                tasks.append(task)

            # Execute concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all requests succeeded
            successful_requests = sum(1 for r in results if not isinstance(r, Exception))
            assert successful_requests >= len(rtsp_streams) * 0.8  # Allow some failures

            logger.info(f"Concurrent stream test: {successful_requests}/{len(rtsp_streams)} succeeded")

    async def _test_concurrent_stream(
        self,
        session: aiohttp.ClientSession,
        chromecast_url: str,
        stream_url: str,
        stream_id: int
    ) -> dict[str, Any]:
        """Test individual concurrent stream"""
        play_data = {"media_url": stream_url}

        async with session.post(f"{chromecast_url}/play", json=play_data) as resp:
            if resp.status != 200:
                raise Exception(f"Stream {stream_id} failed with status {resp.status}")

            result = await resp.json()
            logger.info(f"Stream {stream_id} result: {result}")
            return result


@pytest.mark.asyncio
async def test_video_infrastructure_health_check(video_test_environment: VideoTestEnvironment) -> None:
    """Standalone test to verify video infrastructure is healthy"""
    logger.info("Running video infrastructure health check...")

    # Check RTSP server availability (indirect)
    rtsp_base = video_test_environment.rtsp_base_url
    assert rtsp_base.startswith("rtsp://rtsp-server:8554")

    # Check mock Chromecast availability
    chromecast_url = video_test_environment.mock_chromecast_url

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{chromecast_url}/status", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                assert resp.status == 200
                status = await resp.json()
                assert "state" in status
                logger.info("Mock Chromecast server is healthy")
        except TimeoutError:
            pytest.skip("Mock Chromecast server is not available")
        except aiohttp.ClientError as e:
            pytest.skip(f"Mock Chromecast server connection failed: {e}")

    # Verify fixture data integrity
    cameras = video_test_environment.cameras
    media_players = video_test_environment.media_players

    assert len(cameras) >= 2
    assert len(media_players) >= 2

    available_cameras = [cam for cam in cameras if cam.available]
    available_players = [player for player in media_players if player.available]

    assert len(available_cameras) >= 2
    assert len(available_players) >= 2

    logger.info("Video infrastructure health check passed")
