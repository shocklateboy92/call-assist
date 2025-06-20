#!/bin/bash

# Manual setup script for Call Assist development environment
# Run this if you need to reinstall dependencies manually

set -e  # Exit on any error

echo "🔄 Reinstalling Call Assist development dependencies..."

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Install broker requirements
echo "Installing broker requirements..."
cd "$PROJECT_ROOT/call-assist/addon/broker"
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
cd "$PROJECT_ROOT/call-assist/integration"
if [ -f "test_requirements.txt" ]; then
    echo "  🧪 Installing integration/test_requirements.txt"
    pip install -r test_requirements.txt
fi

# Install Node.js dependencies for Matrix plugin
echo "📦 Installing Node.js dependencies for Matrix plugin..."
cd "$PROJECT_ROOT/call-assist/addon/plugins/matrix"
if [ -f "package.json" ]; then
    echo "  📋 Installing Matrix plugin dependencies"
    npm install
fi

echo "✅ Dependencies reinstalled successfully!"
