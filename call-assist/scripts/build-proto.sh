#!/bin/bash

# Protobuf build script for Call Assist
# This script handles protobuf compilation for all components

set -e  # Exit on any error

echo "Building protobuf files for Call Assist..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Ensure we have grpc tools installed
if ! python -c "import grpc_tools" 2>/dev/null; then
    echo "Error: grpcio-tools not installed. Please install with: pip install grpcio-tools"
    exit 1
fi

# Generate Python protobuf files for broker
echo "Generating Python protobuf files for broker..."
mkdir -p addon/broker/proto_gen
python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=addon/broker \
    --grpc_python_out=addon/broker \
    proto/*.proto

echo "✓ Python protobuf files generated successfully"

# Generate TypeScript protobuf files for Matrix plugin (if protoc-gen-ts is available)
if command -v protoc &> /dev/null && command -v protoc-gen-ts &> /dev/null; then
    echo "Generating TypeScript protobuf files for Matrix plugin..."
    mkdir -p addon/plugins/matrix/src/proto_gen
    protoc \
        --proto_path=proto \
        --ts_out=addon/plugins/matrix/src/proto_gen \
        --grpc-web_out=import_style=typescript,mode=grpcweb:addon/plugins/matrix/src/proto_gen \
        proto/*.proto
    echo "✓ TypeScript protobuf files generated successfully"
else
    echo "⚠ Skipping TypeScript protobuf generation (protoc or protoc-gen-ts not available)"
fi

# Generate C++ protobuf files for XMPP plugin (if protoc is available)
if command -v protoc &> /dev/null; then
    echo "Generating C++ protobuf files for XMPP plugin..."
    mkdir -p addon/plugins/xmpp/proto_gen
    protoc \
        --proto_path=proto \
        --cpp_out=addon/plugins/xmpp/proto_gen \
        --grpc_out=addon/plugins/xmpp/proto_gen \
        --plugin=protoc-gen-grpc=$(which grpc_cpp_plugin 2>/dev/null || echo "grpc_cpp_plugin") \
        proto/*.proto
    echo "✓ C++ protobuf files generated successfully"
else
    echo "⚠ Skipping C++ protobuf generation (protoc not available)"
fi

echo "🎉 Protobuf build completed successfully!"