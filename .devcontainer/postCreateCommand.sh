#!/bin/bash

# Post-create script for Call Assist devcontainer
# This script runs after the devcontainer is created and installs all Python dependencies

set -e  # Exit on any error

echo "🚀 Setting up Call Assist development environment..."

# Configure Python environment for the workspace
echo "📦 Configuring Python environment..."

# Install broker requirements
echo "Installing broker requirements..."
cd /workspaces/universal/call-assist/addon/broker
if [ -f "requirements.txt" ]; then
    echo "  📋 Installing broker/requirements.txt"
    pip install -r requirements.txt
fi

if [ -f "test_requirements.txt" ]; then
    echo "  🧪 Installing broker/test_requirements.txt"
    pip install -r test_requirements.txt
fi

# Install integration requirements
echo "Installing integration requirements..."
cd /workspaces/universal/call-assist/integration
if [ -f "test_requirements.txt" ]; then
    echo "  🧪 Installing integration/test_requirements.txt"
    pip install -r test_requirements.txt
fi

# Build protobuf files
echo "🔧 Building protobuf files..."
cd /workspaces/universal/call-assist
./scripts/build-proto.sh

# Install Node.js dependencies for Matrix plugin
echo "📦 Installing Node.js dependencies for Matrix plugin..."
cd /workspaces/universal/call-assist/addon/plugins/matrix
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

echo "✅ Development environment setup complete!"
echo ""
echo "🎯 Quick start commands:"
echo "  • cd call-assist/addon/broker && ./dev.sh    # Start broker in dev mode"
echo "  • cd call-assist/addon/broker && ./run_all_tests.sh    # Run tests"
echo "  • ./scripts/build-proto.sh    # Rebuild protobuf files"
echo ""
echo "📋 Note: If you need TypeScript protobuf generation for Matrix plugin:"
echo "  • sudo apt-get update && sudo apt-get install -y protobuf-compiler"
echo "  • cd call-assist/addon/plugins/matrix && npm run proto"
echo ""
