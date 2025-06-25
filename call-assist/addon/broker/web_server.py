#!/usr/bin/env python3

import asyncio
import logging
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from ludic.contrib.fastapi import LudicRoute
import uvicorn

from addon.broker.ludic_views import create_routes

logger = logging.getLogger(__name__)


class WebUIServer:
    """Manages the web UI server (Ludic + FastAPI)"""

    def __init__(self, broker_ref=None):
        self.broker_ref = broker_ref
        self.server_task: Optional[asyncio.Task] = None
        self.host = "0.0.0.0"
        self.port = 8080
        self.app: Optional[FastAPI] = None

    async def initialize(self):
        """Initialize web server settings"""
        try:
            # Create FastAPI app with Ludic route class
            self.app = FastAPI(title="Call Assist Broker")
            self.app.router.route_class = LudicRoute
            
            # Add redirect from index to /ui
            @self.app.get("/")
            async def redirect_to_ui():
                return RedirectResponse(url="/ui", status_code=302)
            
            # Setup Ludic routes
            create_routes(self.app, self.broker_ref)

            logger.info(f"Web UI server initialized on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Web UI server initialization failed: {e}")
            raise

    async def start(self):
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

    async def stop(self):
        """Stop the web UI server"""
        try:
            if self.server_task:
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass
            logger.info("Web UI server stopped")
        except Exception as e:
            logger.error(f"Error stopping web UI server: {e}")


def create_web_server(broker_ref=None) -> WebUIServer:
    """Create web UI server with broker reference"""
    return WebUIServer(broker_ref)


# For standalone testing
if __name__ == "__main__":

    async def test_server():
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
