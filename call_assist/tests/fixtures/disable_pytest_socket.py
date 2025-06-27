import logging
from typing import Any

# We can ignore this import for type checking since
# we're only importing it to disable its functionality
import pytest_socket  # type: ignore[import-untyped]

import socket

# Set up logging for tests
logger = logging.getLogger(__name__)


def stub_method(*_: Any, **__: Any) -> None:
    """Stub method to disable pytest-socket"""
    logger.info(
        "pytest-socket disabled. These are integration tests that require network access."
    )


def activate() -> None:
    pytest_socket.disable_socket = stub_method

    # Disable in case it's already enabled
    socket.socket = pytest_socket._true_socket  # type: ignore[reportPrivateUsage]
    socket.socket.connect = pytest_socket._true_connect  # type: ignore[reportPrivateUsage]
