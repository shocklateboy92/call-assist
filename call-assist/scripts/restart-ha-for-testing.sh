#!/bin/bash

# Script to restart Home Assistant and prepare for integration testing

set -e

echo "🔄 Restarting Home Assistant for integration testing..."

# Navigate to project root
cd /workspaces/universal

# Restart Home Assistant container to pick up code changes
echo "📦 Restarting Home Assistant container..."
sudo docker-compose -f call-assist/docker-compose.dev.yml restart homeassistant

# Wait for Home Assistant to be ready
echo "⏳ Waiting for Home Assistant to start..."
timeout=60
counter=0

while [ $counter -lt $timeout ]; do
    if curl -s http://homeassistant:8123/api/ > /dev/null 2>&1; then
        echo "✅ Home Assistant is ready!"
        break
    fi
    echo "   Waiting... ($counter/$timeout seconds)"
    sleep 2
    counter=$((counter + 2))
done

if [ $counter -ge $timeout ]; then
    echo "❌ Home Assistant failed to start within $timeout seconds"
    exit 1
fi

# Check if call_assist integration is already configured and remove it
echo "🧹 Cleaning up existing Call Assist integration..."

# Get auth token (assuming default setup)
AUTH_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0M2ZmZWJmYjFiNTI0N2RlYjQzZjQxMDAxNGFkZDQwOSIsImlhdCI6MTczNDU2MDgzNCwiZXhwIjoyMDQ5OTIwODM0fQ.XObhdfqt6oCQO2N-Pd8Lw1zJF2JfMEKyIojSa_2kK7w"

# Try to get existing config entries for call_assist
echo "🔍 Checking for existing Call Assist configuration..."
EXISTING_ENTRIES=$(curl -s -H "Authorization: Bearer $AUTH_TOKEN" \
    -H "Content-Type: application/json" \
    http://homeassistant:8123/api/config/config_entries | \
    jq -r '.[] | select(.domain == "call_assist") | .entry_id' 2>/dev/null || echo "")

if [ -n "$EXISTING_ENTRIES" ]; then
    echo "🗑️  Found existing Call Assist entries, removing them..."
    for entry_id in $EXISTING_ENTRIES; do
        echo "   Removing entry: $entry_id"
        curl -s -X DELETE \
            -H "Authorization: Bearer $AUTH_TOKEN" \
            -H "Content-Type: application/json" \
            "http://homeassistant:8123/api/config/config_entries/$entry_id" > /dev/null
    done
    echo "✅ Cleaned up existing entries"
else
    echo "ℹ️  No existing Call Assist configuration found"
fi

echo ""
echo "🎉 Home Assistant is ready for integration testing!"
echo "   URL: http://homeassistant:8123"
echo "   API: http://homeassistant:8123/api/"
echo ""