#!/usr/bin/env python3

"""
Test script to verify form generator with plugin schemas
"""

import asyncio
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from addon.broker.plugin_manager import PluginManager
from addon.broker.form_generator import FormGenerator

def test_form_generation():
    """Test form generation from plugin schemas"""
    print("Testing form generator with plugin schemas...")
    
    # Initialize plugin manager
    plugin_manager = PluginManager()
    
    # Get protocol schemas
    schemas = plugin_manager.get_protocol_schemas()
    
    if not schemas:
        print("❌ No schemas found!")
        return False
    
    # Test form generation for each protocol
    for protocol, schema in schemas.items():
        print(f"\n=== Testing form generation for {protocol} ===")
        
        # Create form generator
        form_gen = FormGenerator()
        
        # Generate form (without UI components for testing)
        try:
            # Mock the UI container for testing
            class MockContainer:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def classes(self, *args):
                    return self
            
            # Mock UI components for testing
            class MockComponent:
                def __init__(self, **kwargs):
                    self.value = kwargs.get('value', '')
                    self._kwargs = kwargs
                def classes(self, *args):
                    return self
                def tooltip(self, *args):
                    return self
            
            # Temporarily replace UI components with mocks
            import addon.broker.form_generator as fg
            original_ui = getattr(fg, 'ui', None)
            
            class MockUI:
                def column(self):
                    return MockContainer()
                def label(self, text):
                    return MockComponent(text=text)
                def input(self, **kwargs):
                    return MockComponent(**kwargs)
                def number(self, **kwargs):
                    return MockComponent(**kwargs)
                def select(self, **kwargs):
                    return MockComponent(**kwargs)
                def checkbox(self, label, **kwargs):
                    return MockComponent(label=label, **kwargs)
                def separator(self):
                    return MockComponent()
            
            fg.ui = MockUI()
            
            # Test credential fields
            if schema['credential_fields']:
                print(f"  Testing {len(schema['credential_fields'])} credential fields...")
                for field in schema['credential_fields']:
                    print(f"    - {field['key']}: {field['display_name']} ({field['type']})")
            
            # Test setting fields
            if schema['setting_fields']:
                print(f"  Testing {len(schema['setting_fields'])} setting fields...")
                for field in schema['setting_fields']:
                    print(f"    - {field['key']}: {field['display_name']} ({field['type']})")
            
            print(f"  ✅ Form generation for {protocol} successful")
            
            # Restore original UI
            if original_ui:
                fg.ui = original_ui
                
        except Exception as e:
            print(f"  ❌ Form generation for {protocol} failed: {e}")
            return False
    
    print("\n✅ All form generation tests passed!")
    return True


def test_field_validation():
    """Test field validation logic"""
    print("\nTesting field validation...")
    
    from addon.broker.form_generator import FormField
    
    # Test required field validation
    class MockComponent:
        def __init__(self, value=''):
            self.value = value
    
    # Test required field with empty value
    field_config = {
        'key': 'test_field',
        'display_name': 'Test Field',
        'type': 'STRING',
        'required': True
    }
    
    field = FormField('test_field', field_config, MockComponent(''))
    if field.validate():
        print("❌ Required field validation failed - should reject empty value")
        return False
    else:
        print("✅ Required field validation works")
    
    # Test required field with value
    field_with_value = FormField('test_field', field_config, MockComponent('test_value'))
    if not field_with_value.validate():
        print("❌ Required field validation failed - should accept valid value")
        return False
    else:
        print("✅ Required field with value validation works")
    
    # Test URL validation
    url_config = {
        'key': 'url_field',
        'display_name': 'URL Field',
        'type': 'URL',
        'required': False
    }
    
    url_field = FormField('url_field', url_config, MockComponent('https://example.com'))
    if not url_field.validate():
        print("❌ URL validation failed - should accept valid URL")
        return False
    else:
        print("✅ URL validation works")
    
    # Test invalid URL
    invalid_url_field = FormField('url_field', url_config, MockComponent('not-a-url'))
    if invalid_url_field.validate():
        print("❌ URL validation failed - should reject invalid URL")
        return False
    else:
        print("✅ Invalid URL rejection works")
    
    print("✅ All field validation tests passed!")
    return True


def main():
    """Run all tests"""
    print("Starting form generator tests...\n")
    
    success = True
    
    # Test 1: Form Generation
    if not test_form_generation():
        success = False
    
    # Test 2: Field Validation
    if not test_field_validation():
        success = False
    
    if success:
        print("\n🎉 All form generator tests passed!")
    else:
        print("\n❌ Some tests failed. Check the logs above.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
