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

# Generate Python protobuf files in central location
echo "Generating Python protobuf files in central proto_gen package..."
mkdir -p proto_gen
python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=proto_gen \
    --grpc_python_out=proto_gen \
    --mypy_out=proto_gen \
    proto/*.proto

echo "✓ Python protobuf files generated successfully"

# Fix relative imports in generated files
echo "Fixing Python protobuf imports..."
python scripts/fix-proto-imports.py
echo "✓ Python protobuf imports fixed"

# Generate TypeScript protobuf files for Matrix plugin using ts-proto
if [ -d "addon/plugins/matrix/node_modules" ] && [ -f "addon/plugins/matrix/node_modules/.bin/protoc-gen-ts_proto" ]; then
    echo "Generating TypeScript protobuf files for Matrix plugin..."
    mkdir -p addon/plugins/matrix/src/proto_gen
    cd addon/plugins/matrix
    npm run proto
    cd ../../..
    echo "✓ TypeScript protobuf files generated successfully"
else
    echo "⚠ Skipping TypeScript protobuf generation (dependencies not installed in Matrix plugin)"
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