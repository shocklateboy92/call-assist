#!/usr/bin/env python3
"""
Strong types for test fixtures to replace Any type usage
"""

from dataclasses import dataclass
import threading
from typing import Dict, List, Protocol, Any
import aiohttp
from bs4 import BeautifulSoup

from proto_gen.callassist.broker import BrokerIntegrationStub, HaEntityUpdate


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
    rtsp_streams: List[str]
    cameras: List[HaEntityUpdate]
    media_players: List[HaEntityUpdate]
    mock_chromecast_url: str


class BrokerStub(Protocol):
    """Protocol defining the broker stub interface"""
    async def start_call(self, request: Any, *, timeout: float | None = None) -> Any: ...
    async def health_check(self, request: Any, *, timeout: float | None = None) -> Any: ...


class WebUITestClientProtocol(Protocol):
    """Protocol for the web UI test client"""
    async def get_page(self, path: str) -> tuple[str, BeautifulSoup]: ...
    async def post_form(self, path: str, form_data: Dict[str, str]) -> tuple[int, str, BeautifulSoup]: ...
    async def wait_for_server(self, max_attempts: int = 30, delay: float = 1.0) -> bool: ...