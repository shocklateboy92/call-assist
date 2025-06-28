#!/usr/bin/env python3

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from ludic.contrib.fastapi import LudicRoute

from addon.broker.ludic_views import create_routes

logger = logging.getLogger(__name__)


class WebUIServer:
    """Manages the web UI server (Ludic + FastAPI)"""

    def __init__(self) -> None:
        """Initialize web server (dependencies will be injected via FastAPI DI)"""
        self.server_task: asyncio.Task[None] | None = None
        self.host = "0.0.0.0"
        self.port = 8080
        self.app: FastAPI | None = None

    async def initialize(self) -> None:
        """Initialize web server settings"""
        try:
            # Create FastAPI app with Ludic route class
            self.app = FastAPI(title="Call Assist Broker")
            self.app.router.route_class = LudicRoute

            # Add redirect from index to /ui
            @self.app.get("/")
            async def redirect_to_ui() -> RedirectResponse:
                return RedirectResponse(url="/ui", status_code=302)

            # Setup Ludic routes (dependencies will be injected automatically)
            create_routes(self.app)

            logger.info(f"Web UI server initialized on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Web UI server initialization failed: {e}")
            raise

    async def start(self) -> None:
        """Start the web UI server"""
        try:
            await self.initialize()

            if not self.app:
                raise RuntimeError("App not initialized")

            # Configure Uvicorn server
            config = uvicorn.Config(
                self.app, host=self.host, port=self.port, log_level="info"
            )

            # Start the server in a background task
            server = uvicorn.Server(config)
            self.server_task = asyncio.create_task(server.serve())

            logger.info(f"Web UI server started on http://{self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Failed to start web UI server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the web UI server"""
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
        logger.info("Web UI server stopped")


def create_web_server() -> WebUIServer:
    """Create web UI server (dependencies will be injected via FastAPI DI)"""
    return WebUIServer()


# For standalone testing
if __name__ == "__main__":

    async def test_server() -> None:
        server = WebUIServer()
        await server.start()

        # Keep server running
        try:
            if server.server_task:
                await server.server_task
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        finally:
            await server.stop()

    asyncio.run(test_server())
