#!/usr/bin/env python3

import asyncio
import logging
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import uvicorn
from nicegui import ui

from web_ui import set_broker_reference, setup_ui_routes
from database import init_database, get_setting
from models import get_setting

logger = logging.getLogger(__name__)


class WebUIServer:
    """Manages the web UI server (NiceGUI)"""

    def __init__(self, broker_ref=None):
        self.broker_ref = broker_ref
        self.server_task: Optional[asyncio.Task] = None
        self.host = "0.0.0.0"
        self.port = 8080

    async def initialize(self):
        """Initialize web server settings"""
        try:
            # Initialize database first
            await init_database()

            # Load settings from database
            self.host = get_setting("web_ui_host") or "0.0.0.0"
            self.port = get_setting("web_ui_port") or 8080

            # Set broker reference for UI
            if self.broker_ref:
                set_broker_reference(self.broker_ref)

            # Setup UI routes
            setup_ui_routes()

            logger.info(f"Web UI server initialized on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Web UI server initialization failed: {e}")
            raise

    async def start(self):
        """Start the web UI server"""
        try:
            await self.initialize()

            app = FastAPI()
            
            # Add redirect from index to /ui
            @app.get("/")
            async def redirect_to_ui():
                return RedirectResponse(url="/ui", status_code=302)

            ui.run_with(app, title="Call Assist Web UI", favicon="🎥")

            # Configure NiceGUI server
            config = uvicorn.Config(
                app, host=self.host, port=self.port, log_level="info"
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

    asyncio.run(test_server())
