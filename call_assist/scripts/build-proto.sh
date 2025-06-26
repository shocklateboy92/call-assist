#!/bin/bash

# Protobuf build script for Call Assist
# This script now delegates to the betterproto build script

set -e  # Exit on any error

echo "Building protobuf files for Call Assist (using betterproto)..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the betterproto build script
"$SCRIPT_DIR/build-proto-betterproto.sh"