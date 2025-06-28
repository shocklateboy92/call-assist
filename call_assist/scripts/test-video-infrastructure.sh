#!/bin/bash
set -e

echo "🔍 Testing Video Infrastructure..."

# Navigate to project root for docker-compose commands
cd /workspaces/universal

# Check docker-compose services are running
echo "📋 Checking docker-compose services..."
if docker-compose -f docker-compose.dev.yml ps --services --filter status=running | grep -q rtsp-server; then
    echo "✅ RTSP server service is running"
else
    echo "❌ RTSP server service is not running"
    echo "💡 Try: docker-compose -f docker-compose.dev.yml up -d rtsp-server"
    exit 1
fi

if docker-compose -f docker-compose.dev.yml ps --services --filter status=running | grep -q mock-chromecast; then
    echo "✅ Mock Chromecast service is running"
else
    echo "❌ Mock Chromecast service is not running"
    echo "💡 Try: docker-compose -f docker-compose.dev.yml up -d mock-chromecast"
    exit 1
fi

# Show service health
echo "🔍 Service health:"
docker-compose -f docker-compose.dev.yml ps rtsp-server test-stream-generator test-stream-generator-2 mock-chromecast

# Test streams (requires FFprobe if available)
if command -v ffprobe &> /dev/null; then
    echo "🎥 Testing RTSP streams..."
    
    if timeout 10 ffprobe -v quiet rtsp://localhost:8554/test_camera_1 2>/dev/null; then
        echo "✅ test_camera_1 stream is accessible"
    else
        echo "⚠️  test_camera_1 stream may not be ready yet (this is normal during startup)"
    fi
    
    if timeout 10 ffprobe -v quiet rtsp://localhost:8554/test_camera_2 2>/dev/null; then
        echo "✅ test_camera_2 stream is accessible"
    else
        echo "⚠️  test_camera_2 stream may not be ready yet (this is normal during startup)"
    fi
else
    echo "ℹ️  FFprobe not available - skipping stream content tests"
fi

echo ""
echo ""
echo "🚀 Video infrastructure test complete!"
echo "📍 Available services (via docker-compose network):"
echo "   - RTSP Server: rtsp://rtsp-server:8554"
echo "   - Test Camera 1: rtsp://rtsp-server:8554/test_camera_1"
echo "   - Test Camera 2: rtsp://rtsp-server:8554/test_camera_2"
echo "   - Mock Chromecast: http://mock-chromecast:8008"
echo ""
echo "🧪 Run video tests with:"
echo "   python -m pytest tests/test_video_call_e2e.py::test_video_infrastructure_health_check -v"