#!/bin/bash

# Protobuf build script for Call Assist using betterproto
# This script handles protobuf compilation using betterproto for all components

set -e  # Exit on any error

echo "Building protobuf files with betterproto for Call Assist..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Check if betterproto is installed
if ! python -c "import betterproto" 2>/dev/null; then
    echo "Error: betterproto not installed. Please install with: pip install 'betterproto[compiler]==2.0.0b7'"
    exit 1
fi

# Generate Python protobuf files in central location using betterproto
echo "Generating Python protobuf files with betterproto in central proto_gen package..."
mkdir -p proto_gen
python -m grpc_tools.protoc -I proto \
    --python_betterproto_opt=pydantic_dataclasses \
    --python_betterproto_out=proto_gen \
    proto/*.proto

echo "✓ Python protobuf files generated successfully with betterproto"

# Generate Python protobuf files for Home Assistant integration
echo "Generating Python protobuf files for Home Assistant integration..."
mkdir -p integration/proto_gen
python -m grpc_tools.protoc -I proto \
    --python_betterproto_opt=pydantic_dataclasses \
    --python_betterproto_out=integration/proto_gen \
    proto/*.proto

echo "✓ Integration protobuf files generated successfully with betterproto"

# Generate TypeScript protobuf files for Matrix plugin using ts-proto
if [ -d "addon/plugins/matrix/node_modules" ] && [ -f "addon/plugins/matrix/node_modules/.bin/protoc-gen-ts_proto" ]; then
    echo "Generating TypeScript protobuf files for Matrix plugin..."
    mkdir -p addon/plugins/matrix/src/proto_gen
    cd addon/plugins/matrix
    npm install
    npm run proto
    cd ../../..
    echo "✓ TypeScript protobuf files generated successfully"
else
    echo "⚠ Skipping TypeScript protobuf generation (dependencies not installed in Matrix plugin)"
fi

echo "🎉 Betterproto build completed successfully!"
