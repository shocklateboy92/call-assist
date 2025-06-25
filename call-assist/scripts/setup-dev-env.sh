#!/bin/bash

# Call Assist development environment setup script
# This script sets up the complete development environment including:
# - Python package installation in editable mode
# - Protobuf file generation
# - Node.js dependencies for Matrix plugin

set -e  # Exit on any error

echo "� Setting up Call Assist development environment..."

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Install call-assist package in editable mode first
echo "📦 Installing call-assist package in editable mode..."
cd "$PROJECT_ROOT"
if [ -f "pyproject.toml" ]; then
    echo "  📦 Installing call-assist package in editable mode"
    pip install -e .
    echo "  🧪 Installing test dependencies"
    pip install -e ".[test]"
    echo "  🏠 Installing integration dependencies"
    pip install -e ".[integration]"
else
    echo "  ❌ pyproject.toml not found at $PROJECT_ROOT"
    exit 1
fi

# Broker dependencies are now managed via pyproject.toml
# Integration dependencies are now managed via pyproject.toml

# Build protobuf files
echo "🔧 Building protobuf files..."
cd "$PROJECT_ROOT"
./scripts/build-proto.sh

# Install Node.js dependencies for Matrix plugin
echo "📦 Installing Node.js dependencies for Matrix plugin..."
cd "$PROJECT_ROOT/addon/plugins/matrix"
if [ -f "package.json" ]; then
    echo "  📋 Installing Matrix plugin dependencies"
    npm install
    # Check if protoc is available for TypeScript protobuf generation
    if command -v protoc &> /dev/null; then
        echo "  🔧 Generating TypeScript protobuf files"
        npm run proto || echo "  ⚠️  TypeScript protobuf generation failed (protoc may not be available)"
    else
        echo "  ⚠️  protoc not found - TypeScript protobuf files will need to be generated manually"
        echo "     Install protoc: apt-get update && apt-get install -y protobuf-compiler"
    fi
fi

# Verify installation
echo "  ✅ Verifying installation"
cd "$PROJECT_ROOT"
python -c "import proto_gen, addon.broker, integration; print('✓ All packages available')"

echo "✅ Development environment setup complete!"
echo ""
echo "🔧 Clean imports now available:"
echo "   - import proto_gen.*"
echo "   - from addon.broker import *"
echo "   - from integration import *"
echo "   - from tests import *"
echo ""
echo "🎯 Quick start commands:"
echo "  • cd addon/broker && ./dev.sh    # Start broker in dev mode"
echo "  • cd addon/broker && ./run_all_tests.sh    # Run tests"
echo "  • ./scripts/build-proto.sh    # Rebuild protobuf files"
echo ""
