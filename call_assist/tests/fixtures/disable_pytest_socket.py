import logging
from typing import Any

# We can ignore this import for type checking since
# we're only importing it to disable its functionality
import pytest_socket  # type: ignore[import-untyped]

# Set up logging for tests
logger = logging.getLogger(__name__)


def stub_method(*_: Any, **__: Any) -> None:
    """Stub method to disable pytest-socket"""
    logger.info(
        "pytest-socket disabled. These are integration tests that require network access."
    )


def activate():
    pytest_socket.disable_socket = stub_method
