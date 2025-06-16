#!/bin/bash

# Development startup script for Call Assist Broker

echo "Starting Call Assist Broker in development mode..."

# Change to the broker directory  
cd "$(dirname "$0")"

# Install dependencies if needed
echo "Installing dependencies..."
pip install -r requirements.txt

# Generate protobuf files using central build script
echo "Building protobuf files..."
../../scripts/build-proto.sh

echo "Protobuf files generated successfully"

# Start broker
echo "Starting broker server..."
exec python main.py