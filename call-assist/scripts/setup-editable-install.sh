#!/bin/bash

# Setup script for Call Assist development environment
# This script installs the package in editable mode and sets up dependencies

set -e

echo "Setting up Call Assist development environment..."

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Install the main package in editable mode
echo "Installing call-assist package in editable mode..."
pip install -e .

# Install test dependencies
echo "Installing test dependencies..."
pip install -e ".[test]"

# Install integration test dependencies if needed
echo "Installing integration test dependencies..."
pip install -e ".[integration]"

# Verify installation
echo "Verifying installation..."
python -c "import proto_gen; print('✓ proto_gen package available')"
python -c "import addon.broker; print('✓ broker package available')"
python -c "import integration; print('✓ integration package available')"
python -c "from addon.broker.main import CallAssistBroker; print('✓ CallAssistBroker can be imported')"
python -c "from integration.grpc_client import CallAssistGrpcClient; print('✓ CallAssistGrpcClient can be imported')"

echo ""
echo "✅ Call Assist development environment setup complete!"
echo ""
echo "Key changes made:"
echo "  - Installed call-assist package in editable mode"
echo "  - All sys.path manipulations have been removed"
echo "  - Packages can now be imported normally:"
echo "    - proto_gen.* for protobuf generated code"
echo "    - addon.broker.* for broker functionality"
echo "    - integration.* for Home Assistant integration"
echo "    - tests.* for test utilities"
echo ""
echo "You can now run tests without sys.path issues:"
echo "  cd addon/broker && python -m pytest tests/"
echo "  cd integration && python -m pytest tests/"
echo ""
