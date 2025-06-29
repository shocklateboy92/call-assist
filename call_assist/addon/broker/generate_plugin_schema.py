#!/usr/bin/env python3

"""
Generate JSON Schema for plugin.yaml files using dataclasses-jsonschema.
"""

import json
from typing import Any

from .plugin_manager import PluginMetadata


def generate_plugin_schema() -> dict[str, Any]:
    """Generate JSON Schema for plugin.yaml files"""

    # Generate schema from the PluginMetadata dataclass
    schema = PluginMetadata.json_schema()

    # Add some VS Code specific enhancements
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "Call Assist Plugin Configuration"
    schema["description"] = "Configuration schema for Call Assist plugins"

    return schema


if __name__ == "__main__":
    schema = generate_plugin_schema()

    # Save to file
    with open("plugin-schema.json", "w") as f:
        json.dump(schema, f, indent=2)

    print("Schema generated and saved to plugin-schema.json")
    print("\nTo use in VS Code:")
    print("1. Add to your VS Code settings.json:")
    print('   "yaml.schemas": {')
    print('     "./plugin-schema.json": ["**/plugin.yaml"]')
    print("   }")
    print("2. Or add this line to the top of your plugin.yaml files:")
    print("   # yaml-language-server: $schema=./plugin-schema.json")
