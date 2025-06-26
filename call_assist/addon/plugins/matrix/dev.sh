#!/bin/bash

# Development startup script for Matrix Plugin

echo "Starting Matrix Plugin in development mode..."

# Change to the plugin directory
cd "$(dirname "$0")"

# Install dependencies if needed
echo "Installing dependencies..."
npm install

# Generate protobuf files using central build script
echo "Building protobuf files..."
../../../scripts/build-proto.sh

# Build TypeScript
echo "Building TypeScript..."
npm run build

# Start plugin
echo "Starting Matrix plugin server..."
exec npm start