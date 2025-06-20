#!/bin/bash

# Manual setup script for Call Assist development environment
# Run this if you need to reinstall dependencies manually

set -e  # Exit on any error

echo "🔄 Setting up Call Assist development environment..."

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Set up Call Assist editable package install first
echo "📦 Setting up Call Assist package structure..."
CALL_ASSIST_DIR="$PROJECT_ROOT"
if [ -d "$CALL_ASSIST_DIR" ] && [ -f "$CALL_ASSIST_DIR/pyproject.toml" ]; then
    cd "$CALL_ASSIST_DIR"
    echo "  📦 Installing call-assist package in editable mode"
    pip install -e .
    echo "  🧪 Installing test dependencies"
    pip install -e ".[test]"
    echo "  🏠 Installing integration dependencies"
    pip install -e ".[integration]"
    echo "  ✅ Verifying installation"
    python -c "import proto_gen, addon.broker, integration; print('✓ All packages available')"
else
    echo "  ❌ Call Assist directory or pyproject.toml not found at $CALL_ASSIST_DIR"
    exit 1
fi

# Install remaining broker requirements (if any additional ones exist)
echo "Installing additional broker requirements..."
cd "$PROJECT_ROOT/addon/broker"
if [ -f "requirements.txt" ]; then
    echo "  📋 Checking broker/requirements.txt for additional packages"
    # Only install packages not already covered by the main package install
    pip install -r requirements.txt
fi

if [ -f "test_requirements.txt" ]; then
    echo "  🧪 Checking broker/test_requirements.txt for additional packages"
    pip install -r test_requirements.txt
fi

# Install remaining integration requirements (if any additional ones exist)
echo "Installing additional integration requirements..."
cd "$PROJECT_ROOT/integration"
if [ -f "test_requirements.txt" ]; then
    echo "  🧪 Checking integration/test_requirements.txt for additional packages"
    pip install -r test_requirements.txt
fi

# Install Node.js dependencies for Matrix plugin
echo "📦 Installing Node.js dependencies for Matrix plugin..."
cd "$PROJECT_ROOT/addon/plugins/matrix"
if [ -f "package.json" ]; then
    echo "  📋 Installing Matrix plugin dependencies"
    npm install
fi

echo "✅ Call Assist development environment setup complete!"
echo ""
echo "🔧 You can now use clean imports without sys.path manipulation:"
echo "   - import proto_gen.*"
echo "   - from addon.broker import *"
echo "   - from integration import *"
echo "   - from tests import *"
