#!/usr/bin/env python3
"""
Post-process generated protobuf files to fix relative imports.
This script converts absolute imports to relative imports for proto_gen package.
"""

import os
import glob
import re
import sys


def fix_proto_file(filepath):
    """Fix imports in a single protobuf file"""
    with open(filepath, "r") as f:
        content = f.read()

    # Fix imports in _pb2.py files
    if filepath.endswith("_pb2.py"):
        content = re.sub(
            r"^import common_pb2 as common__pb2$",
            "from . import common_pb2 as common__pb2",
            content,
            flags=re.MULTILINE,
        )

    # Fix imports in _pb2_grpc.py files
    elif filepath.endswith("_pb2_grpc.py"):
        content = re.sub(
            r"^import broker_integration_pb2 as broker__integration__pb2$",
            "from . import broker_integration_pb2 as broker__integration__pb2",
            content,
            flags=re.MULTILINE,
        )
        content = re.sub(
            r"^import call_plugin_pb2 as call__plugin__pb2$",
            "from . import call_plugin_pb2 as call__plugin__pb2",
            content,
            flags=re.MULTILINE,
        )
        content = re.sub(
            r"^import common_pb2 as common__pb2$",
            "from . import common_pb2 as common__pb2",
            content,
            flags=re.MULTILINE,
        )

    with open(filepath, "w") as f:
        f.write(content)


def fix_proto_dir(proto_gen_dir):
    """Fix all protobuf files in a directory"""
    # Fix all protobuf files
    for pattern in ["*_pb2.py", "*_pb2_grpc.py"]:
        for filepath in glob.glob(os.path.join(proto_gen_dir, pattern)):
            print(f"Fixing imports in {os.path.basename(filepath)} ({proto_gen_dir})")
            fix_proto_file(filepath)

    print(f"Proto import fixes completed for {proto_gen_dir}")


def main():
    # Allow directory to be passed as argument, default to central proto_gen
    if len(sys.argv) > 1:
        proto_gen_dir = sys.argv[1]
        if not os.path.isabs(proto_gen_dir):
            # Make relative path absolute from project root
            script_dir = os.path.dirname(__file__)
            project_root = os.path.dirname(script_dir)
            proto_gen_dir = os.path.join(project_root, proto_gen_dir)
    else:
        proto_gen_dir = os.path.join(os.path.dirname(__file__), "..", "proto_gen")

    fix_proto_dir(proto_gen_dir)


if __name__ == "__main__":
    main()
