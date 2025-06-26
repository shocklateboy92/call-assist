#!/bin/bash
set -e

echo "🔍 Testing Video Infrastructure..."

# Test RTSP server availability
echo "📡 Testing RTSP server..."
if timeout 5 bash -c '</dev/tcp/localhost/8554'; then
    echo "✅ RTSP server is accessible on port 8554"
else
    echo "❌ RTSP server is not accessible"
    exit 1
fi

# Test mock Chromecast availability
echo "📱 Testing mock Chromecast..."
if timeout 5 bash -c '</dev/tcp/localhost/8008'; then
    echo "✅ Mock Chromecast is accessible on port 8008"
    
    # Test HTTP endpoint
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8008/status | grep -q "200"; then
        echo "✅ Mock Chromecast HTTP API is working"
    else
        echo "❌ Mock Chromecast HTTP API is not responding"
    fi
else
    echo "❌ Mock Chromecast is not accessible"
    exit 1
fi

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
echo "🚀 Video infrastructure test complete!"
echo "📍 Available services:"
echo "   - RTSP Server: rtsp://localhost:8554"
echo "   - Test Camera 1: rtsp://localhost:8554/test_camera_1"
echo "   - Test Camera 2: rtsp://localhost:8554/test_camera_2"
echo "   - Mock Chromecast: http://localhost:8008"
echo ""
echo "🧪 Run video tests with:"
echo "   python -m pytest tests/test_video_call_e2e.py::test_video_infrastructure_health_check -v"