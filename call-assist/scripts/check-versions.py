#!/usr/bin/env python3
"""
Check version consistency across gRPC/protobuf dependencies.
This script validates that all dependency files and installed packages
use the same versions of gRPC and protobuf.
"""

import subprocess
import sys
import re
import os


def get_version_from_file(filepath, pattern):
    """Extract version from a file using regex pattern"""
    try:
        with open(filepath, "r") as f:
            content = f.read()
            match = re.search(pattern, content)
            return match.group(1) if match else None
    except FileNotFoundError:
        return None


def get_package_version(package):
    """Get installed version of a package"""
    try:
        result = subprocess.run(
            ["pip", "show", package], capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def main():
    """Main version checking logic"""
    print("Checking gRPC/protobuf version consistency...")

    # Define project root relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # Change to project root for relative paths
    os.chdir(project_root)

    # Check main project dependencies
    pyproject_grpc = get_version_from_file(
        "pyproject.toml", r"grpcio>=([0-9.]+\.[0-9.]+)"
    )
    pyproject_grpc_tools = get_version_from_file(
        "pyproject.toml", r"grpcio-tools>=([0-9.]+\.[0-9.]+)"
    )
    broker_grpc = get_version_from_file(
        "addon/broker/requirements.txt", r"grpcio>=([0-9.]+\.[0-9.]+)"
    )
    broker_grpc_tools = get_version_from_file(
        "addon/broker/requirements.txt", r"grpcio-tools>=([0-9.]+\.[0-9.]+)"
    )
    manifest_grpc = get_version_from_file(
        "integration/manifest.json", r'"grpcio>=([0-9.]+\.[0-9.]+)'
    )
    manifest_grpc_tools = get_version_from_file(
        "integration/manifest.json", r'"grpcio-tools>=([0-9.]+\.[0-9.]+)'
    )

    print(f"pyproject.toml grpcio: {pyproject_grpc}")
    print(f"pyproject.toml grpcio-tools: {pyproject_grpc_tools}")
    print(f"broker requirements grpcio: {broker_grpc}")
    print(f"broker requirements grpcio-tools: {broker_grpc_tools}")
    print(f"integration manifest grpcio: {manifest_grpc}")
    print(f"integration manifest grpcio-tools: {manifest_grpc_tools}")

    # Check that all versions match
    versions = [
        pyproject_grpc,
        pyproject_grpc_tools,
        broker_grpc,
        broker_grpc_tools,
        manifest_grpc,
        manifest_grpc_tools,
    ]
    non_null_versions = [v for v in versions if v is not None]

    if not non_null_versions:
        print("ERROR: No gRPC versions found in dependency files!")
        sys.exit(1)

    if not all(v == non_null_versions[0] for v in non_null_versions):
        print("ERROR: gRPC version mismatch across dependency files!")
        print(f"Found versions: {non_null_versions}")
        sys.exit(1)

    expected_version = non_null_versions[0]
    print(f"✓ All gRPC versions consistent: {expected_version}")

    # Check installed versions
    installed_grpc = get_package_version("grpcio")
    installed_grpc_tools = get_package_version("grpcio-tools")
    print(f"Installed grpcio: {installed_grpc}")
    print(f"Installed grpcio-tools: {installed_grpc_tools}")

    if installed_grpc != installed_grpc_tools:
        print("ERROR: Installed gRPC versions do not match!")
        print(f"grpcio: {installed_grpc}, grpcio-tools: {installed_grpc_tools}")
        sys.exit(1)

    # Optionally check if installed version matches expected version
    if installed_grpc and not installed_grpc.startswith(expected_version):
        print(
            f"WARNING: Installed gRPC version ({installed_grpc}) does not match "
            f"expected version ({expected_version})"
        )
        print("Consider updating dependencies or running: pip install -e .")

    print("✓ gRPC/protobuf version consistency check passed")


if __name__ == "__main__":
    main()
