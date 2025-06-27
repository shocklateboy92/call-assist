#!/usr/bin/env python3
"""
Strong types for test fixtures to replace Any type usage
"""

import threading
from dataclasses import dataclass
from typing import Any, Protocol

from bs4 import BeautifulSoup

from proto_gen.callassist.broker import HaEntityUpdate


@dataclass
class BrokerProcessInfo:
    """Information about the running broker process"""
    grpc_port: int
    web_port: int
    db_path: str
    thread: threading.Thread


@dataclass
class VideoTestEnvironment:
    """Complete video testing environment configuration"""
    rtsp_base_url: str
    rtsp_streams: list[str]
    cameras: list[HaEntityUpdate]
    media_players: list[HaEntityUpdate]
    mock_chromecast_url: str


class BrokerStub(Protocol):
    """Protocol defining the broker stub interface"""
    async def start_call(self, request: Any, *, timeout: float | None = None) -> Any: ...
    async def health_check(self, request: Any, *, timeout: float | None = None) -> Any: ...


class WebUITestClientProtocol(Protocol):
    """Protocol for the web UI test client"""
    async def get_page(self, path: str) -> tuple[str, BeautifulSoup]: ...
    async def post_form(self, path: str, form_data: dict[str, str]) -> tuple[int, str, BeautifulSoup]: ...
    async def wait_for_server(self, max_attempts: int = 30, delay: float = 1.0) -> bool: ...


class CustomIntegrationsFixture(Protocol):
    """Protocol for the pytest-homeassistant custom integrations fixture"""


@dataclass
class MatrixApiResponse:
    """Represents a Matrix API response"""
    access_token: str = ""
    user_id: str = ""
    error: str = ""
    room_id: str = ""
