#!/usr/bin/env python3

import asyncio
import logging
import grpc
import grpc.aio
import subprocess
import os
import yaml
from typing import Dict, Optional, List, Union, Literal
from dataclasses import dataclass
from enum import Enum
from dataclasses_jsonschema import JsonSchemaMixin
from dacite import from_dict
from datetime import datetime
from google.protobuf import empty_pb2

import proto_gen.call_plugin_pb2 as cp_pb2
import proto_gen.call_plugin_pb2_grpc as cp_grpc
import proto_gen.common_pb2 as common_pb2

logger = logging.getLogger(__name__)

class PluginState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"

@dataclass
class ExecutableConfig(JsonSchemaMixin):
    """Configuration for plugin executable"""
    type: Literal["node", "python", "binary"]
    command: List[str]
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
    video_codecs: List[str]
    audio_codecs: List[str]
    supported_resolutions: List[ResolutionConfig]
    webrtc_support: bool
    features: Optional[List[str]] = None

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
    required_credentials: Optional[List[str]] = None
    optional_settings: Optional[List[str]] = None
    
    def __post_init__(self):
        # Handle None values for lists
        if self.required_credentials is None:
            self.required_credentials = []
        if self.optional_settings is None:
            self.optional_settings = []

@dataclass
class PluginConfiguration:
    """Configuration state for an initialized plugin"""
    protocol: str
    credentials: Dict[str, str]
    settings: Dict[str, str]
    initialized_at: Optional[str] = None  # ISO timestamp
    is_initialized: bool = True

@dataclass
class PluginInstance:
    metadata: PluginMetadata
    plugin_dir: str
    process: Optional[subprocess.Popen] = None
    channel: Optional[grpc.aio.Channel] = None
    stub: Optional[cp_grpc.CallPluginStub] = None
    state: PluginState = PluginState.STOPPED
    last_error: Optional[str] = None
    configuration: Optional[PluginConfiguration] = None

class PluginManager:
    """Generic plugin manager that loads plugins based on metadata files"""
    
    def __init__(self, plugins_root: Optional[str] = None):
        if plugins_root is None:
            # Default to relative path in dev environment, absolute in production
            current_dir = os.path.dirname(os.path.abspath(__file__))
            plugins_root = os.path.join(os.path.dirname(current_dir), "plugins")
        self.plugins_root = plugins_root
        self.plugins: Dict[str, PluginInstance] = {}
        self._discover_plugins()
    
    def _discover_plugins(self):
        """Discover and load plugin metadata from plugin directories"""
        if not os.path.exists(self.plugins_root):
            logger.warning(f"Plugins directory not found: {self.plugins_root}")
            return
        
        for item in os.listdir(self.plugins_root):
            plugin_dir = os.path.join(self.plugins_root, item)
            if not os.path.isdir(plugin_dir):
                continue
            
            metadata_file = os.path.join(plugin_dir, "plugin.yaml")
            if not os.path.exists(metadata_file):
                logger.debug(f"No plugin.yaml found in {plugin_dir}")
                continue
            
            try:
                metadata = self._load_plugin_metadata(metadata_file)
                self.plugins[metadata.protocol] = PluginInstance(
                    metadata=metadata,
                    plugin_dir=plugin_dir
                )
                logger.info(f"Discovered plugin: {metadata.name} ({metadata.protocol})")
            except Exception as e:
                logger.error(f"Failed to load plugin metadata from {metadata_file}: {e}")
        
        logger.info(f"Plugin discovery complete. Found {len(self.plugins)} plugins")
    
    def _load_plugin_metadata(self, metadata_file: str) -> PluginMetadata:
        """Load and validate plugin metadata from YAML file"""
        with open(metadata_file, 'r') as f:
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
            else:
                logger.warning(f"Plugin {protocol} was marked running but failed health check")
                await self._stop_plugin(plugin)
        
        if plugin.state in [PluginState.STOPPED, PluginState.ERROR]:
            return await self._start_plugin(plugin)
        
        if plugin.state == PluginState.STARTING:
            # Wait for it to finish starting
            timeout = plugin.metadata.grpc.startup_timeout
            for _ in range(timeout):
                await asyncio.sleep(1)
                if plugin.state == PluginState.RUNNING:
                    return True
                if plugin.state == PluginState.ERROR:
                    return False
            
            logger.error(f"Plugin {protocol} timed out during startup")
            return False
        
        return False
    
    async def _start_plugin(self, plugin: PluginInstance) -> bool:
        """Start a plugin process based on its metadata"""
        logger.info(f"Starting plugin: {plugin.metadata.name}")
        plugin.state = PluginState.STARTING
        
        try:
            # Build command from metadata
            exec_config = plugin.metadata.executable
            command = exec_config.command
            working_dir = os.path.join(plugin.plugin_dir, exec_config.working_directory)
            
            # Start the plugin process - pipe output to same console
            plugin.process = subprocess.Popen(
                command,
                stdout=None,  # Inherit stdout from parent process
                stderr=None,  # Inherit stderr from parent process
                cwd=working_dir
            )
            
            # Wait for plugin to start up
            await asyncio.sleep(2)
            
            # Check if process is still running
            if plugin.process.poll() is not None:
                exit_code = plugin.process.returncode
                raise RuntimeError(f"Plugin process exited with code {exit_code}")
            
            # Establish gRPC connection
            port = plugin.metadata.grpc.port
            plugin.channel = grpc.aio.insecure_channel(f'localhost:{port}')
            plugin.stub = cp_grpc.CallPluginStub(plugin.channel)
            
            # Wait for gRPC server to be ready
            health_timeout = plugin.metadata.grpc.health_check_timeout
            for attempt in range(health_timeout * 2):  # 0.5s intervals
                try:
                    await asyncio.wait_for(
                        plugin.stub.GetHealth(empty_pb2.Empty()),
                        timeout=1.0
                    )
                    break
                except (grpc.aio.AioRpcError, asyncio.TimeoutError):
                    if attempt == (health_timeout * 2 - 1):
                        raise
                    await asyncio.sleep(0.5)
            
            plugin.state = PluginState.RUNNING
            logger.info(f"Plugin {plugin.metadata.protocol} started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start plugin {plugin.metadata.protocol}: {e}")
            plugin.state = PluginState.ERROR
            plugin.last_error = str(e)
            await self._cleanup_plugin(plugin)
            return False
    
    async def _stop_plugin(self, plugin: PluginInstance):
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
                        plugin.stub.Shutdown(empty_pb2.Empty()),
                        timeout=5.0
                    )
                except (grpc.aio.AioRpcError, asyncio.TimeoutError):
                    logger.warning(f"Graceful shutdown failed for {plugin.metadata.protocol}")
            
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
            
        except Exception as e:
            logger.error(f"Error stopping plugin {plugin.metadata.protocol}: {e}")
        finally:
            await self._cleanup_plugin(plugin)
            plugin.state = PluginState.STOPPED
    
    async def _cleanup_plugin(self, plugin: PluginInstance):
        """Clean up plugin resources"""
        if plugin.channel:
            try:
                await plugin.channel.close()
            except Exception as e:
                logger.warning(f"Error closing channel for {plugin.metadata.protocol}: {e}")
            plugin.channel = None
        
        plugin.stub = None
        plugin.process = None
    
    async def _health_check(self, plugin: PluginInstance) -> bool:
        """Check if a plugin is healthy"""
        if not plugin.stub:
            return False
        
        try:
            health = await asyncio.wait_for(
                plugin.stub.GetHealth(empty_pb2.Empty()),
                timeout=2.0
            )
            return health.healthy
        except Exception:
            return False
    
    async def initialize_plugin(self, protocol: str, credentials: Dict[str, str], settings: Optional[Dict[str, str]] = None) -> bool:
        """Initialize a plugin with credentials"""
        if not await self.ensure_plugin_running(protocol):
            return False
        
        plugin = self.plugins[protocol]
        if not plugin.stub:
            return False
        
        # Validate required credentials
        missing_creds = []
        for required_cred in (plugin.metadata.required_credentials or []):
            if required_cred not in credentials:
                missing_creds.append(required_cred)
        
        if missing_creds:
            logger.error(f"Missing required credentials for {protocol}: {missing_creds}")
            return False
        
        try:
            config = cp_pb2.PluginConfig(
                protocol=protocol,
                account_id="", # TODO: Add account_id parameter to initialize_plugin
                display_name="", # TODO: Add display_name parameter to initialize_plugin
                credentials=credentials,
                settings=settings or {}
            )
            
            response = await plugin.stub.Initialize(config)
            
            if response.initialized:
                plugin.configuration = PluginConfiguration(
                    protocol=protocol,
                    credentials=credentials,
                    settings=settings or {},
                    initialized_at=datetime.now().isoformat()
                )
                logger.info(f"Plugin {protocol} initialized successfully")
                return True
            else:
                logger.error(f"Plugin {protocol} initialization failed: {response.message}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize plugin {protocol}: {e}")
            return False
    
    async def start_call(self, protocol: str, call_request: cp_pb2.CallStartRequest) -> Optional[cp_pb2.CallStartResponse]:
        """Start a call using the specified protocol plugin"""
        if not await self.ensure_plugin_running(protocol):
            return None
        
        plugin = self.plugins[protocol]
        if not plugin.stub:
            return None
        
        try:
            response = await plugin.stub.StartCall(call_request)
            return response
        except Exception as e:
            logger.error(f"Failed to start call on {protocol}: {e}")
            return None
    
    async def end_call(self, protocol: str, call_request: cp_pb2.CallEndRequest) -> Optional[cp_pb2.CallEndResponse]:
        """End a call using the specified protocol plugin"""
        if protocol not in self.plugins:
            return None
        
        plugin = self.plugins[protocol]
        if not plugin.stub:
            return None
        
        try:
            response = await plugin.stub.EndCall(call_request)
            return response
        except Exception as e:
            logger.error(f"Failed to end call on {protocol}: {e}")
            return None
    
    def get_plugin_capabilities(self, protocol: str) -> Optional[CapabilitiesConfig]:
        """Get capabilities from plugin metadata"""
        if protocol not in self.plugins:
            return None
        
        return self.plugins[protocol].metadata.capabilities
    
    def get_available_protocols(self) -> List[str]:
        """Get list of available protocol plugins"""
        return list(self.plugins.keys())
    
    def get_plugin_state(self, protocol: str) -> Optional[PluginState]:
        """Get the current state of a plugin"""
        if protocol in self.plugins:
            return self.plugins[protocol].state
        return None
    
    def get_plugin_info(self, protocol: str) -> Optional[PluginMetadata]:
        """Get plugin metadata"""
        if protocol in self.plugins:
            return self.plugins[protocol].metadata
        return None
    
    async def initialize_plugin_account(self, protocol: str, account_id: str, display_name: str, credentials: Dict[str, str]) -> bool:
        """Initialize a plugin account with specific account details"""
        if not await self.ensure_plugin_running(protocol):
            return False
        
        plugin = self.plugins[protocol]
        if not plugin.stub:
            return False
        
        # Validate required credentials
        missing_creds = []
        for required_cred in (plugin.metadata.required_credentials or []):
            if required_cred not in credentials:
                missing_creds.append(required_cred)
        
        if missing_creds:
            logger.error(f"Missing required credentials for {protocol}: {missing_creds}")
            return False
        
        try:
            config = cp_pb2.PluginConfig(
                protocol=protocol,
                account_id=account_id,
                display_name=display_name,
                credentials=credentials,
                settings={}
            )
            
            response = await plugin.stub.Initialize(config)
            
            if response.initialized:
                plugin.configuration = PluginConfiguration(
                    protocol=protocol,
                    credentials=credentials,
                    settings={},
                    initialized_at=datetime.now().isoformat()
                )
                logger.info(f"Plugin {protocol} account {account_id} initialized successfully")
                return True
            else:
                logger.error(f"Plugin {protocol} account {account_id} initialization failed: {response.message}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize plugin {protocol} account {account_id}: {e}")
            return False
    
    def get_plugin_instance(self, protocol: str, account_id: str) -> Optional['PluginInstance']:
        """Get plugin instance for a specific account"""
        # For now, just return the main plugin instance
        # In the future, this could support multiple instances per protocol
        if protocol in self.plugins:
            return self.plugins[protocol]
        return None
    
    async def start_call_on_account(self, protocol: str, account_id: str, call_request: cp_pb2.CallStartRequest) -> Optional[cp_pb2.CallStartResponse]:
        """Start a call on a specific account"""
        # For now, just use the main plugin instance
        return await self.start_call(protocol, call_request)
    
    async def end_call_on_account(self, protocol: str, account_id: str, call_request: cp_pb2.CallEndRequest) -> Optional[cp_pb2.CallEndResponse]:
        """End a call on a specific account"""
        # For now, just use the main plugin instance
        return await self.end_call(protocol, call_request)

    async def shutdown_all(self):
        """Shutdown all running plugins"""
        logger.info("Shutting down all plugins")
        
        tasks = []
        for plugin in self.plugins.values():
            if plugin.state in [PluginState.RUNNING, PluginState.STARTING]:
                tasks.append(self._stop_plugin(plugin))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("All plugins shut down")