#!/bin/bash
set -e

echo "=== Call Assist Broker Integration Tests ==="
echo "Setting up test environment..."

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BROKER_DIR="$SCRIPT_DIR"

# Install test dependencies
echo "Installing test dependencies..."
cd "$BROKER_DIR"
pip install -r test_requirements.txt

# Build protobuf files if needed
echo "Building protobuf files..."
cd "$(dirname "$BROKER_DIR")"
if [ -f "../scripts/build-proto.sh" ]; then
    ../scripts/build-proto.sh
else
    echo "Warning: build-proto.sh not found, assuming protobufs are already built"
fi

cd "$BROKER_DIR"

# Run the tests
echo "Running integration tests..."
python -m pytest test_integration.py -v --tb=short

echo "Integration tests completed!"
