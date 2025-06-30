#!/usr/bin/env python3

import asyncio
import atexit
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import FrameType
from typing import Literal, Optional

import betterproto.lib.pydantic.google.protobuf as betterproto_lib_pydantic_google_protobuf
import yaml
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin
from grpclib.client import Channel
from grpclib.exceptions import GRPCError

from proto_gen.callassist.plugin import (
    CallEndRequest,
    CallEndResponse,
    CallPluginStub,
    CallStartRequest,
    CallStartResponse,
    PluginConfig,
)

from .data_types import ProtocolSchemaDict

logger = logging.getLogger(__name__)


class PluginState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class FieldDefinition(JsonSchemaMixin):
    """Definition for a credential or setting field with UI metadata"""

    key: str
    display_name: str
    description: str = ""
    type: Literal["STRING", "PASSWORD", "URL", "INTEGER", "BOOLEAN", "SELECT"] = (
        "STRING"
    )
    required: bool = False
    default_value: str = ""
    sensitive: bool = False  # Whether to mask the field in UI
    allowed_values: list[str] | None = None  # For SELECT type
    placeholder: str = ""  # Placeholder text for UI
    validation_pattern: str = ""  # Regex pattern for validation


@dataclass
class ExecutableConfig(JsonSchemaMixin):
    """Configuration for plugin executable"""

    type: Literal["node", "python", "binary"]
    command: list[str]
    working_directory: str = "."


@dataclass
class GrpcConfig(JsonSchemaMixin):
    """Configuration for plugin gRPC service"""

    port: int
    health_check_timeout: int = 5
    startup_timeout: int = 30


@dataclass
class ResolutionConfig(JsonSchemaMixin):
    """Resolution configuration that maps to protobuf Resolution"""

    width: int
    height: int
    framerate: int


@dataclass
class CapabilitiesConfig(JsonSchemaMixin):
    """Configuration for plugin capabilities"""

    video_codecs: list[str]
    audio_codecs: list[str]
    supported_resolutions: list[ResolutionConfig]
    webrtc_support: bool
    features: list[str] | None = None


@dataclass
class PluginMetadata(JsonSchemaMixin):
    """Strongly typed plugin metadata structure"""

    name: str
    protocol: str
    executable: ExecutableConfig
    grpc: GrpcConfig
    capabilities: CapabilitiesConfig
    version: str = "1.0.0"
    description: str = ""
    required_credentials: list[str] | None = None
    optional_settings: list[str] | None = None
    credential_fields: list[FieldDefinition] | None = (
        None  # UI metadata for credentials
    )
    setting_fields: list[FieldDefinition] | None = None  # UI metadata for settings

    def __post_init__(self) -> None:
        # Handle None values for lists
        if self.required_credentials is None:
            self.required_credentials = []
        if self.optional_settings is None:
            self.optional_settings = []
        if self.credential_fields is None:
            self.credential_fields = []
        if self.setting_fields is None:
            self.setting_fields = []

        # Auto-generate rich field definitions from simple lists if not provided
        if not self.credential_fields and self.required_credentials:
            self.credential_fields = [
                FieldDefinition(
                    key=cred,
                    display_name=cred.replace("_", " ").title(),
                    description=f"Enter your {cred.replace('_', ' ')}",
                    type=(
                        "PASSWORD"
                        if any(
                            secret_word in cred.lower()
                            for secret_word in ["password", "token", "secret", "key"]
                        )
                        else "STRING"
                    ),
                    required=True,
                    sensitive=any(
                        secret_word in cred.lower()
                        for secret_word in ["password", "token", "secret", "key"]
                    ),
                )
                for cred in self.required_credentials
            ]

        if not self.setting_fields and self.optional_settings:
            self.setting_fields = [
                FieldDefinition(
                    key=setting,
                    display_name=setting.replace("_", " ").title(),
                    description=f"Configure {setting.replace('_', ' ')}",
                    type="STRING",
                    required=False,
                )
                for setting in self.optional_settings
            ]


@dataclass
class PluginConfiguration:
    """Configuration state for an initialized plugin"""

    protocol: str
    credentials: dict[str, str]
    settings: dict[str, str]
    initialized_at: str | None = None  # ISO timestamp
    is_initialized: bool = True


@dataclass
class PluginInstance:
    metadata: PluginMetadata
    plugin_dir: str
    process: subprocess.Popen[bytes] | None = None
    channel: Channel | None = None
    stub: CallPluginStub | None = None
    state: PluginState = PluginState.STOPPED
    last_error: str | None = None
    configuration: PluginConfiguration | None = None


class PluginManager:
    """Generic plugin manager that loads plugins based on metadata files"""

    def __init__(self, plugins_root: str | None = None):
        if plugins_root is None:
            # Default to relative path in dev environment, absolute in production
            current_dir = Path(__file__).resolve().parent
            plugins_root = str(current_dir.parent / "plugins")
        self.plugins_root = plugins_root
        self.plugins: dict[str, PluginInstance] = {}
        self._shutdown_requested = False

        # Register cleanup handlers
        atexit.register(self._emergency_cleanup)

        # Only register signal handlers if we're in the main thread
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGINT, self._signal_handler)
                logger.debug("Signal handlers registered for plugin cleanup")
            except ValueError as e:
                logger.debug(f"Could not register signal handlers: {e}")
        else:
            logger.debug("Not in main thread, skipping signal handler registration")

        self._discover_plugins()

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle termination signals"""
        logger.info(f"Received signal {signum}, initiating plugin shutdown...")
        self._shutdown_requested = True

        # Run the shutdown in the event loop if it exists
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.shutdown_all())
        except RuntimeError:
            # No event loop running, do emergency cleanup
            self._emergency_cleanup()

        # Exit after cleanup
        sys.exit(0)

    def _emergency_cleanup(self) -> None:
        """Emergency cleanup of plugins without async/await"""
        if self._shutdown_requested:
            return  # Already cleaning up

        self._shutdown_requested = True
        logger.warning("Emergency cleanup: forcefully terminating all plugin processes")

        for protocol, plugin in self.plugins.items():
            if plugin.process and plugin.process.poll() is None:
                try:
                    logger.info(
                        f"Force terminating plugin {protocol} (PID: {plugin.process.pid})"
                    )
                    plugin.process.terminate()

                    # Wait briefly for graceful termination
                    try:
                        plugin.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            f"Plugin {protocol} did not terminate gracefully, killing..."
                        )
                        plugin.process.kill()
                        plugin.process.wait()

                    logger.info(f"Plugin {protocol} terminated")
                except ProcessLookupError as e:
                    logger.debug(
                        f"Plugin {protocol} process cleanup error (likely already dead): {e}"
                    )
                except (OSError, RuntimeError) as e:
                    logger.error(
                        f"Error during emergency cleanup of plugin {protocol}: {e}"
                    )

    def __del__(self) -> None:
        """Destructor to ensure plugins are cleaned up"""
        if hasattr(self, "_shutdown_requested") and not self._shutdown_requested:
            self._emergency_cleanup()

    def _find_available_port(
        self, start_port: int = 50051, max_attempts: int = 100
    ) -> int:
        """Find an available port starting from start_port"""
        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("localhost", port))
                    return port
            except OSError:
                continue
        raise RuntimeError(
            f"Could not find an available port in range {start_port}-{start_port + max_attempts}"
        )

    def _discover_plugins(self) -> None:
        """Discover and load plugin metadata from plugin directories"""
        if not Path(self.plugins_root).exists():
            logger.warning(f"Plugins directory not found: {self.plugins_root}")
            return

        for plugin_dir in Path(self.plugins_root).iterdir():
            if not plugin_dir.is_dir():
                continue

            metadata_file = plugin_dir / "plugin.yaml"
            if not metadata_file.exists():
                logger.debug(f"No plugin.yaml found in {plugin_dir}")
                continue

            try:
                metadata = self._load_plugin_metadata(str(metadata_file))
                self.plugins[metadata.protocol] = PluginInstance(
                    metadata=metadata, plugin_dir=str(plugin_dir)
                )
                logger.info(f"Discovered plugin: {metadata.name} ({metadata.protocol})")
            except (OSError, ValueError, TypeError) as e:
                logger.error(
                    f"Failed to load plugin metadata from {metadata_file}: {e}"
                )

        logger.info(f"Plugin discovery complete. Found {len(self.plugins)} plugins")

    def _load_plugin_metadata(self, metadata_file: str) -> PluginMetadata:
        """Load and validate plugin metadata from YAML file"""
        with Path(metadata_file).open() as f:
            data = yaml.safe_load(f)

        # Use dacite to automatically deserialize into strongly typed dataclasses
        try:
            return from_dict(data_class=PluginMetadata, data=data)
        except Exception as e:
            raise ValueError(f"Invalid plugin metadata structure: {e}") from e

    async def ensure_plugin_running(self, protocol: str) -> bool:
        """Ensure a plugin is running, starting it if necessary"""
        if protocol not in self.plugins:
            logger.error(f"Unknown protocol: {protocol}")
            return False

        plugin = self.plugins[protocol]

        if plugin.state == PluginState.RUNNING:
            # Verify it's actually responsive
            if await self._health_check(plugin):
                return True
            logger.warning(
                f"Plugin {protocol} was marked running but failed health check"
            )
            await self._stop_plugin(plugin)

        if plugin.state in [PluginState.STOPPED, PluginState.ERROR]:
            return await self._start_plugin(plugin)

        if plugin.state == PluginState.STARTING:
            # Wait for it to finish starting
            timeout = plugin.metadata.grpc.startup_timeout
            return await self._wait_for_plugin_startup(plugin, timeout)

        return False

    async def _wait_for_plugin_startup(
        self, plugin: PluginInstance, timeout: int
    ) -> bool:
        """Wait for plugin to finish starting up"""
        for _ in range(timeout):
            await asyncio.sleep(1)
            # Check if plugin has finished starting
            if plugin.state == PluginState.RUNNING:
                return True
            if plugin.state == PluginState.ERROR:
                return False

        logger.error(f"Plugin {plugin.metadata.protocol} timed out during startup")
        return False

    async def _start_plugin(self, plugin: PluginInstance) -> bool:
        """Start a plugin process based on its metadata"""
        logger.info(f"Starting plugin: {plugin.metadata.name}")
        plugin.state = PluginState.STARTING

        try:
            # Find an available port for this plugin
            available_port = self._find_available_port()
            logger.info(
                f"Assigned port {available_port} to plugin {plugin.metadata.name}"
            )

            # Update the plugin's gRPC configuration with the new port
            plugin.metadata.grpc.port = available_port

            # Build command from metadata
            exec_config = plugin.metadata.executable
            command = exec_config.command
            working_dir = str(Path(plugin.plugin_dir) / exec_config.working_directory)

            # Set up environment variables
            env = os.environ.copy()
            env["PORT"] = str(available_port)

            # Start the plugin process - pipe output to same console
            plugin.process = subprocess.Popen(
                command,
                stdout=None,  # Inherit stdout from parent process
                stderr=None,  # Inherit stderr from parent process
                cwd=working_dir,
                env=env,
            )

            # Wait for plugin to start up
            await asyncio.sleep(0.2)

            # Check if process is still running
            if plugin.process.poll() is not None:
                exit_code = plugin.process.returncode
                raise RuntimeError(f"Plugin process exited with code {exit_code}")

            # Establish gRPC connection
            port = plugin.metadata.grpc.port
            plugin.channel = Channel(host="localhost", port=port)
            plugin.stub = CallPluginStub(plugin.channel)

            # Wait for gRPC server to be ready
            health_timeout = plugin.metadata.grpc.health_check_timeout
            for attempt in range(health_timeout * 2):  # 0.5s intervals
                try:
                    await asyncio.wait_for(
                        plugin.stub.get_health(
                            betterproto_lib_pydantic_google_protobuf.Empty()
                        ),
                        timeout=1.0,
                    )
                    break
                except (TimeoutError, Exception):
                    if attempt == (health_timeout * 2 - 1):
                        raise
                    await asyncio.sleep(0.5)

            plugin.state = PluginState.RUNNING
            logger.info(f"Plugin {plugin.metadata.protocol} started successfully")
            return True

        except (RuntimeError, TimeoutError) as e:
            logger.error(f"Failed to start plugin {plugin.metadata.protocol}: {e}")
            plugin.state = PluginState.ERROR
            plugin.last_error = str(e)
            await self._cleanup_plugin(plugin)
            return False

    async def _stop_plugin(self, plugin: PluginInstance) -> None:
        """Stop a running plugin"""
        if plugin.state == PluginState.STOPPED:
            return

        logger.info(f"Stopping plugin: {plugin.metadata.name}")
        plugin.state = PluginState.STOPPING

        try:
            # Try graceful shutdown via gRPC
            if plugin.stub:
                try:
                    await asyncio.wait_for(
                        plugin.stub.shutdown(
                            betterproto_lib_pydantic_google_protobuf.Empty()
                        ),
                        timeout=5.0,
                    )
                except (TimeoutError, Exception):
                    logger.warning(
                        f"Graceful shutdown failed for {plugin.metadata.protocol}"
                    )

            # Terminate process
            if plugin.process:
                try:
                    plugin.process.terminate()
                    await asyncio.sleep(2)
                    if plugin.process.poll() is None:
                        plugin.process.kill()
                        await asyncio.sleep(1)
                except ProcessLookupError:
                    pass  # Process already gone

        except (OSError, RuntimeError) as e:
            logger.error(f"Error stopping plugin {plugin.metadata.protocol}: {e}")
        finally:
            await self._cleanup_plugin(plugin)
            plugin.state = PluginState.STOPPED

    async def _cleanup_plugin(self, plugin: PluginInstance) -> None:
        """Clean up plugin resources"""
        if plugin.channel:
            try:
                plugin.channel.close()
            except (OSError, RuntimeError) as e:
                logger.warning(
                    f"Error closing channel for {plugin.metadata.protocol}: {e}"
                )
            plugin.channel = None

        plugin.stub = None
        plugin.process = None

    async def _health_check(self, plugin: PluginInstance) -> bool:
        """Check if a plugin is healthy"""
        if not plugin.stub:
            return False

        try:
            health = await asyncio.wait_for(
                plugin.stub.get_health(
                    betterproto_lib_pydantic_google_protobuf.Empty()
                ),
                timeout=2.0,
            )
            return health.healthy
        except (TimeoutError, GRPCError, ConnectionError, OSError):
            return False

    async def initialize_plugin(
        self,
        protocol: str,
        credentials: dict[str, str],
        settings: dict[str, str] | None = None,
    ) -> bool:
        """Initialize a plugin with credentials"""
        if not await self.ensure_plugin_running(protocol):
            return False

        plugin = self.plugins[protocol]
        if not plugin.stub:
            return False

        # Validate required credentials
        missing_creds = []
        for required_cred in plugin.metadata.required_credentials or []:
            if required_cred not in credentials:
                missing_creds.append(required_cred)

        if missing_creds:
            logger.error(
                f"Missing required credentials for {protocol}: {missing_creds}"
            )
            return False

        try:
            config = PluginConfig(
                protocol=protocol,
                account_id="",  # TODO: Add account_id parameter to initialize_plugin
                display_name="",  # TODO: Add display_name parameter to initialize_plugin
                credentials=credentials,
                settings=settings or {},
            )

            response = await plugin.stub.initialize(config)

            if response.initialized:
                plugin.configuration = PluginConfiguration(
                    protocol=protocol,
                    credentials=credentials,
                    settings=settings or {},
                    initialized_at=datetime.now().isoformat(),
                )
                logger.info(f"Plugin {protocol} initialized successfully")
                return True
            logger.error(f"Plugin {protocol} initialization failed: {response.message}")
            return False

        except (TimeoutError, GRPCError, ConnectionError, OSError) as e:
            logger.error(f"Failed to initialize plugin {protocol}: {e}")
            return False

    async def start_call(
        self, protocol: str, call_request: CallStartRequest
    ) -> CallStartResponse | None:
        """Start a call using the specified protocol plugin"""
        if not await self.ensure_plugin_running(protocol):
            return None

        plugin = self.plugins[protocol]
        if not plugin.stub:
            return None

        try:
            return await plugin.stub.start_call(call_request)
        except (TimeoutError, GRPCError, ConnectionError, OSError) as e:
            logger.error(f"Failed to start call on {protocol}: {e}")
            return None

    async def end_call(
        self, protocol: str, call_request: CallEndRequest
    ) -> CallEndResponse | None:
        """End a call using the specified protocol plugin"""
        if protocol not in self.plugins:
            return None

        plugin = self.plugins[protocol]
        if not plugin.stub:
            return None

        try:
            return await plugin.stub.end_call(call_request)
        except (TimeoutError, GRPCError, ConnectionError, OSError) as e:
            logger.error(f"Failed to end call on {protocol}: {e}")
            return None

    def get_plugin_capabilities(self, protocol: str) -> CapabilitiesConfig | None:
        """Get capabilities from plugin metadata"""
        if protocol not in self.plugins:
            return None

        return self.plugins[protocol].metadata.capabilities

    def get_available_protocols(self) -> list[str]:
        """Get list of available protocol plugins"""
        return list(self.plugins.keys())

    def get_plugin_state(self, protocol: str) -> PluginState | None:
        """Get the current state of a plugin"""
        if protocol in self.plugins:
            return self.plugins[protocol].state
        return None

    def get_plugin_info(self, protocol: str) -> PluginMetadata | None:
        """Get plugin metadata"""
        if protocol in self.plugins:
            return self.plugins[protocol].metadata
        return None

    async def initialize_plugin_account(
        self,
        protocol: str,
        account_id: str,
        display_name: str,
        credentials: dict[str, str],
    ) -> bool:
        """Initialize a plugin account with specific account details"""
        if not await self.ensure_plugin_running(protocol):
            return False

        plugin = self.plugins[protocol]
        if not plugin.stub:
            return False

        # Validate required credentials
        missing_creds = []
        for required_cred in plugin.metadata.required_credentials or []:
            if required_cred not in credentials:
                missing_creds.append(required_cred)

        if missing_creds:
            logger.error(
                f"Missing required credentials for {protocol}: {missing_creds}"
            )
            return False

        try:
            config = PluginConfig(
                protocol=protocol,
                account_id=account_id,
                display_name=display_name,
                credentials=credentials,
                settings={},
            )

            response = await plugin.stub.initialize(config)

            if response.initialized:
                plugin.configuration = PluginConfiguration(
                    protocol=protocol,
                    credentials=credentials,
                    settings={},
                    initialized_at=datetime.now().isoformat(),
                )
                logger.info(
                    f"Plugin {protocol} account {account_id} initialized successfully"
                )
                return True
            logger.error(
                f"Plugin {protocol} account {account_id} initialization failed: {response.message}"
            )
            return False

        except (TimeoutError, GRPCError, ConnectionError, OSError) as e:
            logger.error(
                f"Failed to initialize plugin {protocol} account {account_id}: {e}"
            )
            return False

    def get_plugin_instance(
        self, protocol: str, account_id: str
    ) -> Optional["PluginInstance"]:
        """Get plugin instance for a specific account"""
        # For now, just return the main plugin instance
        # In the future, this could support multiple instances per protocol
        if protocol in self.plugins:
            return self.plugins[protocol]
        return None

    def get_protocol_schemas(self) -> dict[str, ProtocolSchemaDict]:
        """Get UI schemas for all available protocols"""
        schemas: dict[str, ProtocolSchemaDict] = {}

        for protocol, plugin_instance in self.plugins.items():
            metadata = plugin_instance.metadata

            # Convert plugin metadata to UI schema format
            schema: ProtocolSchemaDict = {
                "protocol": protocol,
                "display_name": metadata.name,
                "description": metadata.description,
                "credential_fields": [
                    {
                        "key": field.key,
                        "display_name": field.display_name,
                        "description": field.description,
                        "type": field.type,
                        "required": field.required,
                        "default_value": field.default_value,
                        "sensitive": field.sensitive,
                        "allowed_values": field.allowed_values or [],
                        "placeholder": field.placeholder,
                        "validation_pattern": field.validation_pattern,
                    }
                    for field in (metadata.credential_fields or [])
                ],
                "setting_fields": [
                    {
                        "key": field.key,
                        "display_name": field.display_name,
                        "description": field.description,
                        "type": field.type,
                        "required": field.required,
                        "default_value": field.default_value,
                        "sensitive": field.sensitive,
                        "allowed_values": field.allowed_values or [],
                        "placeholder": field.placeholder,
                        "validation_pattern": field.validation_pattern,
                    }
                    for field in (metadata.setting_fields or [])
                ],
                "example_account_ids": [f"user@{protocol}.example.com", "example_user"],
                "capabilities": {
                    "video_codecs": metadata.capabilities.video_codecs,
                    "audio_codecs": metadata.capabilities.audio_codecs,
                    "webrtc_support": metadata.capabilities.webrtc_support,
                    "features": metadata.capabilities.features or [],
                },
            }

            schemas[protocol] = schema

        return schemas

    async def shutdown_all(self) -> None:
        """Shutdown all running plugins"""
        if self._shutdown_requested:
            return  # Already shutting down

        self._shutdown_requested = True
        logger.info("Shutting down all plugins")

        tasks = []
        for plugin in self.plugins.values():
            if plugin.state in [PluginState.RUNNING, PluginState.STARTING]:
                tasks.append(self._stop_plugin(plugin))

        if tasks:
            try:
                # Wait for all plugins to stop gracefully with a timeout
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=10.0
                )
            except TimeoutError:
                logger.warning("Graceful shutdown timed out, forcing termination")
                # Force terminate any remaining processes
                for plugin in self.plugins.values():
                    if plugin.process and plugin.process.poll() is None:
                        try:
                            logger.warning(
                                f"Force killing plugin {plugin.metadata.protocol}"
                            )
                            plugin.process.kill()
                        except (ProcessLookupError, OSError):
                            pass  # Process already dead

        logger.info("All plugins shut down")
