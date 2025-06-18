#!/bin/bash

# Comprehensive integration test runner for Call Assist

set -e

echo "🧪 Call Assist Integration Test Runner"
echo "======================================"

# Navigate to project root
cd /workspaces/universal

# Step 1: Fix protobuf imports
echo ""
echo "🔧 Step 1: Fixing protobuf imports..."

# Copy protobuf files to integration directory
echo "   Copying protobuf files..."
cp call-assist/addon/broker/broker_integration_pb2.py call-assist/integration/
cp call-assist/addon/broker/broker_integration_pb2_grpc.py call-assist/integration/
cp call-assist/addon/broker/common_pb2.py call-assist/integration/

# Also copy the type stub files if they exist
if [ -f call-assist/addon/broker/broker_integration_pb2.pyi ]; then
    cp call-assist/addon/broker/broker_integration_pb2.pyi call-assist/integration/
fi
if [ -f call-assist/addon/broker/common_pb2.pyi ]; then
    cp call-assist/addon/broker/common_pb2.pyi call-assist/integration/
fi

echo "✅ Protobuf files copied to integration directory"

# Step 2: Update imports in grpc_client.py and test files
echo ""
echo "🔧 Step 2: Updating import paths..."

# Fix the import paths in grpc_client.py to use local files
sed -i 's|^# Import protobuf generated files.*$|# Import protobuf generated files|' call-assist/integration/grpc_client.py
sed -i 's|^import sys.*$||' call-assist/integration/grpc_client.py
sed -i 's|^import os.*$||' call-assist/integration/grpc_client.py
sed -i 's|^sys\.path\.append.*$||' call-assist/integration/grpc_client.py
sed -i '/^$/N;/^\n$/d' call-assist/integration/grpc_client.py  # Remove empty lines

# Replace the imports to use local files
sed -i 's|from broker_integration_pb2_grpc|from .broker_integration_pb2_grpc|' call-assist/integration/grpc_client.py
sed -i 's|from broker_integration_pb2|from .broker_integration_pb2|' call-assist/integration/grpc_client.py
sed -i 's|from common_pb2|from .common_pb2|' call-assist/integration/grpc_client.py

# Also copy protobuf files to tests directory for broker_test_utils
cp call-assist/addon/broker/broker_integration_pb2.py call-assist/tests/
cp call-assist/addon/broker/broker_integration_pb2_grpc.py call-assist/tests/
cp call-assist/addon/broker/common_pb2.py call-assist/tests/
cp call-assist/addon/broker/empty_pb2.py call-assist/tests/ 2>/dev/null || echo "   empty_pb2.py not found, skipping"

echo "✅ Import paths updated"

# Step 3: Install test dependencies
echo ""
echo "📦 Step 3: Installing test dependencies..."
pip install aiohttp > /dev/null 2>&1 || echo "   aiohttp already installed"

# Step 4: Restart Home Assistant and clean up
echo ""
echo "🔄 Step 4: Restarting Home Assistant..."
./call-assist/scripts/restart-ha-for-testing.sh

# Step 4.5: Try to get a valid token
echo ""
echo "🔑 Step 4.5: Attempting to get valid auth token..."
TOKEN_RESULT=$(python3 call-assist/scripts/get-ha-token.py 2>/dev/null | grep "Token:" | cut -d' ' -f2)
if [ -n "$TOKEN_RESULT" ]; then
    echo "✅ Got valid token, updating test file..."
    # Update the token in the test file
    sed -i "s/DEFAULT_AUTH_TOKEN = .*/DEFAULT_AUTH_TOKEN = \"$TOKEN_RESULT\"/" call-assist/tests/test_integration_api.py
else
    echo "⚠️  Could not get token automatically, using existing token"
fi

# Step 5: Run integration tests
echo ""
echo "🧪 Step 5: Running integration tests..."
echo ""

# Set Python path to include our test directory
export PYTHONPATH="/workspaces/universal/call-assist/tests:$PYTHONPATH"

# Run the integration tests
python3 /workspaces/universal/call-assist/tests/test_integration_api.py

# Capture test result
TEST_RESULT=$?

echo ""
echo "======================================"
if [ $TEST_RESULT -eq 0 ]; then
    echo "🎉 Integration tests completed successfully!"
else
    echo "😞 Integration tests failed!"
fi
echo "======================================"

exit $TEST_RESULT