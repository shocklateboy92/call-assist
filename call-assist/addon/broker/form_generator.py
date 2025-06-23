#!/usr/bin/env python3

from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, create_model
from nicegui import ui
import logging

logger = logging.getLogger(__name__)


class FormField:
    """Represents a form field with its UI component and validation"""

    def __init__(self, key: str, field_config: Dict[str, Any], ui_component: Any):
        self.key = key
        self.config = field_config
        self.component = ui_component
        self.validation_errors = []

    @property
    def value(self):
        """Get current field value"""
        return self.component.value if hasattr(self.component, "value") else None

    @value.setter
    def value(self, val):
        """Set field value"""
        if hasattr(self.component, "value"):
            self.component.value = val

    def validate(self) -> bool:
        """Validate field value"""
        self.validation_errors.clear()

        # Required field validation
        if self.config.get("required", False) and not self.value:
            self.validation_errors.append(
                f"{self.config.get('display_name', self.key)} is required"
            )
            return False

        # Type-specific validation
        field_type = self.config.get("type", "STRING")

        if field_type == "URL" and self.value:
            if not self._is_valid_url(self.value):
                self.validation_errors.append(f"Invalid URL format")
                return False

        elif field_type == "INTEGER" and self.value is not None:
            try:
                int(self.value)
            except (ValueError, TypeError):
                self.validation_errors.append(f"Must be a valid integer")
                return False

        return True

    def _is_valid_url(self, url: str) -> bool:
        """Basic URL validation"""
        import re

        url_pattern = re.compile(
            r"^https?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )
        return url_pattern.match(url) is not None


class FormGenerator:
    """Generates forms dynamically from schema definitions"""

    def __init__(self):
        self.fields: Dict[str, FormField] = {}
        self.container = None

    def generate_form(
        self, schema: Dict[str, Any], container: Optional[ui.column] = None
    ) -> Dict[str, FormField]:
        """Generate form fields from schema definition"""
        if container is None:
            container = ui.column().classes("w-full gap-2")

        self.container = container
        self.fields.clear()

        with container:
            # Generate credential fields
            credential_fields = schema.get("credential_fields", [])
            if credential_fields:
                ui.label("Credentials").classes("text-subtitle1 q-mt-md")
                for field_config in credential_fields:
                    self._create_form_field(field_config)

            # Generate setting fields
            setting_fields = schema.get("setting_fields", [])
            if setting_fields:
                ui.label("Settings").classes("text-subtitle1 q-mt-md")
                for field_config in setting_fields:
                    self._create_form_field(field_config)

        return self.fields

    def _create_form_field(self, field_config: Dict[str, Any]) -> FormField:
        """Create a single form field based on configuration"""
        key = field_config["key"]
        field_type = field_config.get("type", "STRING")

        # Common properties
        label = field_config.get("display_name", key.title())
        placeholder = field_config.get("description", "")
        default_value = field_config.get("default_value", "")
        required = field_config.get("required", False)
        sensitive = field_config.get("sensitive", False)

        # Add required indicator to label
        if required:
            label += " *"

        # Create UI component based on type
        component = None

        if field_type in ["STRING", "PASSWORD"]:
            component = ui.input(
                label=label,
                placeholder=placeholder,
                value=default_value,
                password=sensitive or field_type == "PASSWORD",
            ).classes("w-full")

        elif field_type == "URL":
            component = ui.input(
                label=label,
                placeholder=placeholder or "https://example.com",
                value=default_value,
            ).classes("w-full")

        elif field_type == "INTEGER":
            component = ui.number(
                label=label, value=int(default_value) if default_value else None
            ).classes("w-full")

        elif field_type == "SELECT":
            options = field_config.get("allowed_values", [])
            component = ui.select(
                label=label,
                options=options,
                value=default_value if default_value in options else None,
            ).classes("w-full")

        elif field_type == "BOOLEAN":
            component = ui.checkbox(
                label, value=bool(default_value) if default_value else False
            )

        else:
            # Default to string input
            component = ui.input(
                label=label, placeholder=placeholder, value=default_value
            ).classes("w-full")

        # Add description as tooltip if available
        if field_config.get("description"):
            component.tooltip(field_config["description"])

        # Create form field wrapper
        form_field = FormField(key, field_config, component)
        self.fields[key] = form_field

        return form_field

    def validate_form(self) -> tuple[bool, List[str]]:
        """Validate all form fields"""
        all_errors = []
        is_valid = True

        for field in self.fields.values():
            if not field.validate():
                is_valid = False
                all_errors.extend(field.validation_errors)

        return is_valid, all_errors

    def get_form_data(self) -> Dict[str, Any]:
        """Get current form data as dictionary"""
        return {key: field.value for key, field in self.fields.items()}

    def set_form_data(self, data: Dict[str, Any]):
        """Set form data from dictionary"""
        for key, value in data.items():
            if key in self.fields:
                self.fields[key].value = value

    def clear_form(self):
        """Clear all form fields"""
        for field in self.fields.values():
            if hasattr(field.component, "value"):
                default_value = field.config.get("default_value", "")
                field.component.value = default_value

    def show_validation_errors(self, errors: List[str]):
        """Show validation errors to user"""
        for error in errors:
            ui.notify(error, type="negative")


def create_account_form(protocol_schema: Dict[str, Any]) -> FormGenerator:
    """Create a complete account form for a specific protocol"""
    form_gen = FormGenerator()

    # Add protocol info
    with ui.column().classes("w-full gap-2") as container:
        # Protocol header
        ui.label(protocol_schema.get("display_name", "Account")).classes("text-h6")
        if protocol_schema.get("description"):
            ui.label(protocol_schema["description"]).classes("text-caption text-grey")

        # Account identification fields
        ui.label("Account Information").classes("text-subtitle1 q-mt-md")

        # Account ID field
        example_ids = protocol_schema.get("example_account_ids", [])
        placeholder = f"e.g., {example_ids[0]}" if example_ids else "Account identifier"

        account_id_field = ui.input(
            label="Account ID *", placeholder=placeholder, value=""
        ).classes("w-full")

        display_name_field = ui.input(
            label="Display Name *",
            placeholder="Friendly name for this account",
            value="",
        ).classes("w-full")

        # Generate schema-based fields
        form_gen.generate_form(protocol_schema, container)

        # Add account ID and display name to fields
        form_gen.fields["account_id"] = FormField(
            "account_id",
            {"required": True, "display_name": "Account ID", "type": "STRING"},
            account_id_field,
        )
        form_gen.fields["display_name"] = FormField(
            "display_name",
            {"required": True, "display_name": "Display Name", "type": "STRING"},
            display_name_field,
        )

    return form_gen


def create_settings_form(settings_schema: Dict[str, Any]) -> FormGenerator:
    """Create a settings form"""
    form_gen = FormGenerator()

    with ui.column().classes("w-full gap-2") as container:
        ui.label("Settings").classes("text-h6")
        form_gen.generate_form(settings_schema, container)

    return form_gen


# Predefined schemas for common use cases
BROKER_SETTINGS_SCHEMA = {
    "display_name": "Broker Settings",
    "description": "Configure Call Assist Broker behavior",
    "setting_fields": [
        {
            "key": "web_ui_port",
            "display_name": "Web UI Port",
            "description": "Port for the web interface",
            "type": "INTEGER",
            "required": True,
            "default_value": "8080",
        },
        {
            "key": "web_ui_host",
            "display_name": "Web UI Host",
            "description": "Host/IP address for the web interface",
            "type": "STRING",
            "required": True,
            "default_value": "0.0.0.0",
        },
        {
            "key": "enable_call_history",
            "display_name": "Enable Call History",
            "description": "Store call history in database",
            "type": "BOOLEAN",
            "required": False,
            "default_value": True,
        },
        {
            "key": "max_call_history_days",
            "display_name": "Max Call History (days)",
            "description": "Number of days to keep call history",
            "type": "INTEGER",
            "required": False,
            "default_value": "30",
        },
        {
            "key": "auto_cleanup_logs",
            "display_name": "Auto Cleanup Logs",
            "description": "Automatically clean up old call logs",
            "type": "BOOLEAN",
            "required": False,
            "default_value": True,
        },
    ],
}
