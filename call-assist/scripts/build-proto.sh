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

# Check for version consistency across gRPC/protobuf dependencies
python scripts/check-versions.py

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
python scripts/fix-proto-imports.py proto_gen
echo "✓ Python protobuf imports fixed"

# Generate Python protobuf files for Home Assistant integration
echo "Generating Python protobuf files for Home Assistant integration..."
mkdir -p integration/proto_gen
python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=integration/proto_gen \
    --grpc_python_out=integration/proto_gen \
    --mypy_out=integration/proto_gen \
    proto/*.proto

echo "✓ Integration protobuf files generated successfully"

# Fix relative imports in integration files
echo "Fixing integration protobuf imports..."
python scripts/fix-proto-imports.py integration/proto_gen
echo "✓ Integration protobuf imports fixed"

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

echo "🎉 Protobuf build completed successfully!"