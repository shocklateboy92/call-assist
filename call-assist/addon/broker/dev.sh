#!/bin/bash

# Development startup script for Call Assist Broker

echo "Starting Call Assist Broker in development mode..."

# Change to the broker directory  
cd "$(dirname "$0")"

# Install dependencies if needed
echo "Setting up development environment..."
# Check if the call-assist package is installed in editable mode
if ! python -c "import proto_gen, addon.broker" 2>/dev/null; then
    echo "📦 Call Assist package not properly installed, running setup..."
    cd ../..
    if [ -f "scripts/setup-editable-install.sh" ]; then
        ./scripts/setup-editable-install.sh
    else
        # Fallback to root setup script
        ../../scripts/setup-dev-env.sh
    fi
    cd addon/broker
else
    echo "✅ Call Assist package already available"
fi

# Generate protobuf files using central build script
echo "Building protobuf files..."
../../scripts/build-proto.sh

echo "Protobuf files generated successfully"

# Start broker
echo "Starting broker server..."
exec python main.py