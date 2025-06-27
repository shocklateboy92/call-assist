#!/usr/bin/env python3
"""
Mock Chromecast Server for Testing

Simulates Chromecast behavior for testing media player integration.
This server provides HTTP endpoints that mimic Chromecast's casting protocol.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import WSMsgType, web

logger = logging.getLogger(__name__)


class MockChromecastServer:
    """Mock server that simulates Chromecast protocol for testing"""

    def __init__(self) -> None:
        self.app = web.Application()
        self._setup_routes()

        # Server state
        self.current_media: str | None = None
        self.state: str = "idle"
        self.volume: float = 0.5
        self.websockets: set[web.WebSocketResponse] = set()
        self.supported_formats = ["mp4", "webm", "rtsp", "hls"]

    def _setup_routes(self) -> None:
        """Set up HTTP routes for Chromecast simulation"""
        self.app.router.add_post('/play', self.handle_play)
        self.app.router.add_post('/stop', self.handle_stop)
        self.app.router.add_post('/pause', self.handle_pause)
        self.app.router.add_post('/volume', self.handle_volume)
        self.app.router.add_get('/status', self.handle_status)
        self.app.router.add_get('/ws', self.handle_websocket)

    async def handle_play(self, request: web.Request) -> web.Response:
        """Handle media play requests"""
        try:
            data = await request.json()
            media_url = data.get('media_url')

            if not media_url:
                return web.json_response(
                    {"error": "media_url is required"},
                    status=400
                )

            self.current_media = media_url
            self.state = "playing"

            logger.info(f"Mock Chromecast now playing: {media_url}")

            # Notify websocket clients
            await self._broadcast_state_change()

            return web.json_response({
                "status": "success",
                "state": self.state,
                "media_url": self.current_media,
                "timestamp": datetime.now(UTC).isoformat()
            })

        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400
            )
        except Exception as e:
            logger.error(f"Error in handle_play: {e}")
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

    async def handle_stop(self, request: web.Request) -> web.Response:
        """Handle media stop requests"""
        self.current_media = None
        self.state = "idle"

        logger.info("Mock Chromecast stopped playing")

        await self._broadcast_state_change()

        return web.json_response({
            "status": "success",
            "state": self.state,
            "timestamp": datetime.now(UTC).isoformat()
        })

    async def handle_pause(self, request: web.Request) -> web.Response:
        """Handle media pause requests"""
        if self.state == "playing":
            self.state = "paused"
        elif self.state == "paused":
            self.state = "playing"

        logger.info(f"Mock Chromecast state changed to: {self.state}")

        await self._broadcast_state_change()

        return web.json_response({
            "status": "success",
            "state": self.state,
            "media_url": self.current_media,
            "timestamp": datetime.now(UTC).isoformat()
        })

    async def handle_volume(self, request: web.Request) -> web.Response:
        """Handle volume control requests"""
        try:
            data = await request.json()
            volume_level = data.get('volume_level')

            if volume_level is None:
                return web.json_response(
                    {"error": "volume_level is required"},
                    status=400
                )

            if not 0.0 <= volume_level <= 1.0:
                return web.json_response(
                    {"error": "volume_level must be between 0.0 and 1.0"},
                    status=400
                )

            self.volume = volume_level
            logger.info(f"Mock Chromecast volume set to: {volume_level}")

            await self._broadcast_state_change()

            return web.json_response({
                "status": "success",
                "volume": self.volume,
                "timestamp": datetime.now(UTC).isoformat()
            })

        except json.JSONDecodeError:
            return web.json_response(
                {"error": "Invalid JSON"},
                status=400
            )

    async def handle_status(self, request: web.Request) -> web.Response:
        """Return current player status"""
        return web.json_response({
            "state": self.state,
            "media_url": self.current_media,
            "volume": self.volume,
            "supported_formats": self.supported_formats,
            "timestamp": datetime.now(UTC).isoformat(),
            "device_info": {
                "name": "Mock Chromecast",
                "model": "Test Device v1.0",
                "manufacturer": "Call Assist Testing"
            }
        })

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle websocket connections for real-time updates"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websockets.add(ws)
        logger.info("New websocket client connected")

        # Send current state to new client
        await self._send_state_to_client(ws)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_websocket_command(ws, data)
                    except json.JSONDecodeError:
                        await ws.send_str(json.dumps({
                            "error": "Invalid JSON"
                        }))
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
        finally:
            self.websockets.discard(ws)
            logger.info("WebSocket client disconnected")

        return ws

    async def _handle_websocket_command(self, ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
        """Handle commands received via websocket"""
        command = data.get('command')

        if command == 'get_status':
            await self._send_state_to_client(ws)
        elif command == 'ping':
            await ws.send_str(json.dumps({
                "type": "pong",
                "timestamp": datetime.now(UTC).isoformat()
            }))
        else:
            await ws.send_str(json.dumps({
                "error": f"Unknown command: {command}"
            }))

    async def _send_state_to_client(self, ws: web.WebSocketResponse) -> None:
        """Send current state to a specific websocket client"""
        try:
            await ws.send_str(json.dumps({
                "type": "state_update",
                "state": self.state,
                "media_url": self.current_media,
                "volume": self.volume,
                "timestamp": datetime.now(UTC).isoformat()
            }))
        except Exception as e:
            logger.error(f"Failed to send state to client: {e}")

    async def _broadcast_state_change(self) -> None:
        """Broadcast state changes to all connected websockets"""
        if not self.websockets:
            return

        message = json.dumps({
            "type": "state_change",
            "state": self.state,
            "media_url": self.current_media,
            "volume": self.volume,
            "timestamp": datetime.now(UTC).isoformat()
        })

        # Remove closed websockets and send to active ones
        dead_ws = set()
        for ws in self.websockets:
            try:
                await ws.send_str(message)
            except ConnectionResetError:
                dead_ws.add(ws)
            except Exception as e:
                logger.error(f"Error broadcasting to websocket: {e}")
                dead_ws.add(ws)

        self.websockets -= dead_ws

        if dead_ws:
            logger.info(f"Removed {len(dead_ws)} dead websocket connections")


async def create_app() -> web.Application:
    """Create and configure the mock Chromecast server application"""
    server = MockChromecastServer()
    return server.app


def main() -> None:
    """Main entry point for running the mock server"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("Starting Mock Chromecast Server...")

    app = asyncio.run(create_app())
    web.run_app(app, host="0.0.0.0", port=8008)


if __name__ == "__main__":
    main()
