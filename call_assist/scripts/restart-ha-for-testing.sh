#!/bin/bash

# Script to restart Home Assistant and prepare for integration testing

set -e

echo "🔄 Restarting Home Assistant for integration testing..."

# Navigate to project root
cd /workspaces/universal

# Restart Home Assistant container to pick up code changes
echo "📦 Restarting Home Assistant container..."
sudo docker-compose -f call_assist/docker-compose.dev.yml restart homeassistant

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

echo ""
echo "🎉 Home Assistant is ready for integration testing!"
echo "   URL: http://homeassistant:8123"
echo "   API: http://homeassistant:8123/api/"
echo ""