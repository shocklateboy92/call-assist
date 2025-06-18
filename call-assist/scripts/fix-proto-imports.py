#!/usr/bin/env python3
"""
Post-process generated protobuf files to fix relative imports.
This script converts absolute imports to relative imports for proto_gen package.
"""

import os
import glob
import re

def fix_proto_file(filepath):
    """Fix imports in a single protobuf file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Fix imports in _pb2.py files
    if filepath.endswith('_pb2.py'):
        content = re.sub(r'^import common_pb2 as common__pb2$', 'from . import common_pb2 as common__pb2', content, flags=re.MULTILINE)
    
    # Fix imports in _pb2_grpc.py files
    elif filepath.endswith('_pb2_grpc.py'):
        content = re.sub(r'^import broker_integration_pb2 as broker__integration__pb2$', 'from . import broker_integration_pb2 as broker__integration__pb2', content, flags=re.MULTILINE)
        content = re.sub(r'^import call_plugin_pb2 as call__plugin__pb2$', 'from . import call_plugin_pb2 as call__plugin__pb2', content, flags=re.MULTILINE)
        content = re.sub(r'^import common_pb2 as common__pb2$', 'from . import common_pb2 as common__pb2', content, flags=re.MULTILINE)
    
    with open(filepath, 'w') as f:
        f.write(content)

def main():
    proto_gen_dir = os.path.join(os.path.dirname(__file__), '..', 'proto_gen')
    
    # Fix all protobuf files
    for pattern in ['*_pb2.py', '*_pb2_grpc.py']:
        for filepath in glob.glob(os.path.join(proto_gen_dir, pattern)):
            print(f"Fixing imports in {os.path.basename(filepath)}")
            fix_proto_file(filepath)
    
    print("Proto import fixes completed")

if __name__ == '__main__':
    main()