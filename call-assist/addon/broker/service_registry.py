#!/usr/bin/env python3
"""
Service registry for dynamically registered broker services.

This module provides a strongly typed framework for defining and executing
services that can be dynamically registered with Home Assistant.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Union, Type, get_type_hints
from inspect import signature, Parameter

from proto_gen.callassist.broker import (
    ServiceDefinition,
    ServiceField,
    ServiceFieldType,
    ServiceFieldValidation,
    ServiceExecutionRequest,
    ServiceExecutionResponse,
)

logger = logging.getLogger(__name__)


class ServiceFieldTypeMapping(Enum):
    """Maps Python types to protobuf ServiceFieldType."""
    STRING = ServiceFieldType.STRING
    INTEGER = ServiceFieldType.INTEGER
    BOOLEAN = ServiceFieldType.BOOLEAN
    SELECT = ServiceFieldType.SELECT
    ENTITY = ServiceFieldType.ENTITY
    DURATION = ServiceFieldType.DURATION


@dataclass
class ServiceFieldConfig:
    """Configuration for a service field with validation."""
    display_name: str
    description: str
    required: bool = True
    options: List[str] = field(default_factory=list)
    default_value: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    regex_pattern: Optional[str] = None


@dataclass
class ServiceConfig:
    """Configuration for a service."""
    display_name: str
    description: str
    icon: str = "mdi:cog"
    required_capabilities: List[str] = field(default_factory=list)


class ServiceParameter:
    """Decorator for service parameters to add metadata."""
    
    def __init__(
        self,
        display_name: str,
        description: str,
        required: bool = True,
        options: Optional[List[str]] = None,
        default_value: Optional[str] = None,
        **validation_kwargs
    ):
        self.config = ServiceFieldConfig(
            display_name=display_name,
            description=description,
            required=required,
            options=options or [],
            default_value=default_value,
            **validation_kwargs
        )
    
    def __call__(self, func):
        """Allow using as decorator."""
        return func


def service_parameter(
    display_name: str,
    description: str,
    required: bool = True,
    options: Optional[List[str]] = None,
    default_value: Optional[str] = None,
    **validation_kwargs
) -> ServiceParameter:
    """Function-based parameter decorator."""
    return ServiceParameter(
        display_name=display_name,
        description=description,
        required=required,
        options=options,
        default_value=default_value,
        **validation_kwargs
    )


class BrokerService(ABC):
    """Base class for broker services."""
    
    def __init__(self, service_config: ServiceConfig):
        self.config = service_config
        self._field_configs: Dict[str, ServiceFieldConfig] = {}
        self._parse_method_signature()
    
    def _parse_method_signature(self) -> None:
        """Parse the execute method signature to extract field configurations."""
        execute_method = getattr(self, 'execute', None)
        if not execute_method:
            raise ValueError("Service must implement execute method")
        
        # Get parameter metadata from annotations
        if hasattr(execute_method, '__annotations__'):
            annotations = execute_method.__annotations__
            for param_name, annotation in annotations.items():
                if param_name in ('self', 'return'):
                    continue
                
                # Look for ServiceParameter instance in the class
                field_config = getattr(self.__class__, f"_{param_name}_config", None)
                if field_config is None:
                    # Create default config from annotation
                    field_config = ServiceFieldConfig(
                        display_name=param_name.replace('_', ' ').title(),
                        description=f"Parameter: {param_name}",
                        required=True
                    )
                
                self._field_configs[param_name] = field_config
    
    def get_service_definition(self) -> ServiceDefinition:
        """Generate service definition from metadata."""
        execute_method = getattr(self, 'execute', None)
        if not execute_method:
            raise ValueError("Service must implement execute method")
        
        sig = signature(execute_method)
        type_hints = get_type_hints(execute_method)
        
        fields = []
        
        # Check if method uses **kwargs (which means we should use all field configs)
        has_kwargs = any(param.kind == Parameter.VAR_KEYWORD for param in sig.parameters.values())
        
        if has_kwargs:
            # Use all field configs when **kwargs is used
            for param_name, field_config in self._field_configs.items():
                # Map Python type to protobuf field type (default to string)
                field_type = self._map_python_type_to_service_field_type(str)
                
                # Create validation
                validation = ServiceFieldValidation()
                if field_config.min_length is not None:
                    validation.min_length = field_config.min_length
                if field_config.max_length is not None:
                    validation.max_length = field_config.max_length
                if field_config.min_value is not None:
                    validation.min_value = field_config.min_value
                if field_config.max_value is not None:
                    validation.max_value = field_config.max_value
                if field_config.regex_pattern is not None:
                    validation.regex_pattern = field_config.regex_pattern
                
                service_field = ServiceField(
                    key=param_name,
                    display_name=field_config.display_name,
                    field_type=field_type,
                    required=field_config.required,
                    description=field_config.description,
                    options=field_config.options,
                    default_value=field_config.default_value or "",
                    validation=validation
                )
                fields.append(service_field)
        else:
            # Use signature-based discovery for methods with named parameters
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                field_config = self._field_configs.get(param_name)
                if not field_config:
                    continue
                
                # Map Python type to protobuf field type
                param_type = type_hints.get(param_name, str)
                field_type = self._map_python_type_to_service_field_type(param_type)
                
                # Create validation
                validation = ServiceFieldValidation()
                if field_config.min_length is not None:
                    validation.min_length = field_config.min_length
                if field_config.max_length is not None:
                    validation.max_length = field_config.max_length
                if field_config.min_value is not None:
                    validation.min_value = field_config.min_value
                if field_config.max_value is not None:
                    validation.max_value = field_config.max_value
                if field_config.regex_pattern is not None:
                    validation.regex_pattern = field_config.regex_pattern
                
                service_field = ServiceField(
                    key=param_name,
                    display_name=field_config.display_name,
                    field_type=field_type,
                    required=field_config.required,
                    description=field_config.description,
                    options=field_config.options,
                    default_value=field_config.default_value or "",
                    validation=validation
                )
                fields.append(service_field)
        
        return ServiceDefinition(
            service_name=self.__class__.__name__.lower().replace('service', ''),
            display_name=self.config.display_name,
            description=self.config.description,
            fields=fields,
            required_capabilities=self.config.required_capabilities,
            icon=self.config.icon
        )
    
    @staticmethod
    def _map_python_type_to_service_field_type(python_type: Type) -> ServiceFieldType:
        """Map Python type to ServiceFieldType."""
        if python_type == str:
            return ServiceFieldType.STRING
        elif python_type == int:
            return ServiceFieldType.INTEGER
        elif python_type == bool:
            return ServiceFieldType.BOOLEAN
        else:
            return ServiceFieldType.STRING
    
    def validate_parameters(self, parameters: Dict[str, str]) -> Dict[str, Any]:
        """Validate and convert parameters to correct types."""
        execute_method = getattr(self, 'execute', None)
        if not execute_method:
            raise ValueError("Service must implement execute method")
        
        sig = signature(execute_method)
        type_hints = get_type_hints(execute_method)
        validated_params = {}
        
        # Check if method uses **kwargs (which means we should use all field configs)
        has_kwargs = any(param.kind == Parameter.VAR_KEYWORD for param in sig.parameters.values())
        
        if has_kwargs:
            # Use all field configs when **kwargs is used
            for param_name, field_config in self._field_configs.items():
                param_value = parameters.get(param_name)
                
                # Check required fields
                if field_config.required and not param_value:
                    raise ValueError(f"Required parameter '{param_name}' is missing")
                
                # Use default if not provided
                if not param_value and field_config.default_value:
                    param_value = field_config.default_value
                
                # Convert to correct type (default to string for **kwargs)
                if param_value:
                    # For **kwargs, we don't have type hints, so use string unless it's a numeric field
                    if param_name.endswith('_minutes') or param_name.endswith('_count') or param_name.endswith('_number'):
                        try:
                            validated_params[param_name] = int(param_value)
                        except ValueError:
                            validated_params[param_name] = param_value
                    else:
                        validated_params[param_name] = param_value
        else:
            # Use signature-based validation for methods with named parameters
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                
                field_config = self._field_configs.get(param_name)
                if not field_config:
                    continue
                
                param_value = parameters.get(param_name)
                
                # Check required fields
                if field_config.required and not param_value:
                    raise ValueError(f"Required parameter '{param_name}' is missing")
                
                # Use default if not provided
                if not param_value and field_config.default_value:
                    param_value = field_config.default_value
                
                # Convert to correct type
                if param_value:
                    param_type = type_hints.get(param_name, str)
                    if param_type == int:
                        validated_params[param_name] = int(param_value)
                    elif param_type == bool:
                        validated_params[param_name] = param_value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        validated_params[param_name] = param_value
        
        return validated_params
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the service with validated parameters."""
        pass


class ServiceRegistry:
    """Registry for managing broker services."""
    
    def __init__(self):
        self.services: Dict[str, BrokerService] = {}
    
    def register_service(self, service: BrokerService) -> None:
        """Register a service."""
        service_name = service.__class__.__name__.lower().replace('service', '')
        self.services[service_name] = service
        logger.info(f"Registered service: {service_name}")
    
    def unregister_service(self, service_name: str) -> None:
        """Unregister a service."""
        if service_name in self.services:
            del self.services[service_name]
            logger.info(f"Unregistered service: {service_name}")
    
    def get_service_definitions(self) -> List[ServiceDefinition]:
        """Get all service definitions."""
        definitions = []
        for service in self.services.values():
            try:
                definition = service.get_service_definition()
                definitions.append(definition)
            except Exception as ex:
                logger.error(f"Failed to get definition for service {service.__class__.__name__}: {ex}")
        return definitions
    
    async def execute_service(self, request: ServiceExecutionRequest) -> ServiceExecutionResponse:
        """Execute a service."""
        service = self.services.get(request.service_name)
        if not service:
            return ServiceExecutionResponse(
                success=False,
                message=f"Service '{request.service_name}' not found",
                result_data={},
                timestamp=datetime.now(timezone.utc)
            )
        
        try:
            # Validate parameters
            validated_params = service.validate_parameters(dict(request.parameters))
            
            # Execute service
            result = await service.execute(**validated_params)
            
            return ServiceExecutionResponse(
                success=True,
                message=result.get('message', 'Service executed successfully'),
                result_data=result.get('data', {}),
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as ex:
            logger.error(f"Service execution failed for {request.service_name}: {ex}")
            return ServiceExecutionResponse(
                success=False,
                message=f"Service execution failed: {str(ex)}",
                result_data={},
                timestamp=datetime.now(timezone.utc)
            )


# Global service registry instance
service_registry = ServiceRegistry()
