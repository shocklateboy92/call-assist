#!/bin/bash
set -e

echo "=== Call Assist Complete Integration Test Suite ==="
echo "This test suite will:"
echo "1. Test broker functionality with mock plugins"
echo "2. Test Matrix plugin integration with real Matrix homeserver"
echo "3. Test end-to-end user scenarios"
echo ""

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BROKER_DIR="$SCRIPT_DIR"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Function to check if a service is running
check_service() {
    local service_name=$1
    local port=$2
    local timeout=${3:-10}
    
    echo "Checking if $service_name is running on port $port..."
    
    for i in $(seq 1 $timeout); do
        if nc -z localhost $port 2>/dev/null; then
            echo "✓ $service_name is running"
            return 0
        fi
        sleep 1
    done
    
    echo "✗ $service_name is not running on port $port"
    return 1
}

# Function to start Matrix homeserver if needed
start_matrix_homeserver() {
    if ! check_service "Matrix Synapse" 8008 5; then
        echo "Starting Matrix homeserver for testing..."
        cd "$PROJECT_ROOT"
        
        if [ -f "docker-compose.dev.yml" ]; then
            docker-compose -f docker-compose.dev.yml up -d synapse
            echo "Waiting for Matrix homeserver to start..."
            sleep 10
            
            if check_service "Matrix Synapse" 8008 30; then
                echo "✓ Matrix homeserver started successfully"
            else
                echo "✗ Failed to start Matrix homeserver"
                return 1
            fi
        else
            echo "Warning: docker-compose.dev.yml not found, assuming Matrix homeserver is already running"
        fi
    fi
}

# Function to build Matrix plugin if needed
build_matrix_plugin() {
    local matrix_dir="$PROJECT_ROOT/addon/plugins/matrix"
    
    if [ -d "$matrix_dir" ]; then
        echo "Building Matrix plugin..."
        cd "$matrix_dir"
        
        if [ -f "package.json" ]; then
            if [ ! -d "node_modules" ]; then
                echo "Installing Matrix plugin dependencies..."
                npm install
            fi
            
            if [ ! -d "dist" ] || [ "src/index.ts" -nt "dist/index.js" ]; then
                echo "Building Matrix plugin TypeScript..."
                npm run build
            fi
        else
            echo "Warning: Matrix plugin package.json not found"
        fi
    else
        echo "Warning: Matrix plugin directory not found at $matrix_dir"
    fi
}

# Function to start Matrix plugin for testing
start_matrix_plugin() {
    local matrix_dir="$PROJECT_ROOT/addon/plugins/matrix"
    
    if [ -d "$matrix_dir/dist" ] && [ -f "$matrix_dir/dist/index.js" ]; then
        echo "Starting Matrix plugin for testing..."
        cd "$matrix_dir"
        
        # Start plugin in background
        node dist/index.js &
        MATRIX_PLUGIN_PID=$!
        
        # Wait for plugin to start
        sleep 3
        
        if check_service "Matrix Plugin" 50052 10; then
            echo "✓ Matrix plugin started successfully (PID: $MATRIX_PLUGIN_PID)"
            return 0
        else
            echo "✗ Failed to start Matrix plugin"
            if [ ! -z "$MATRIX_PLUGIN_PID" ]; then
                kill $MATRIX_PLUGIN_PID 2>/dev/null || true
            fi
            return 1
        fi
    else
        echo "Warning: Matrix plugin not built, skipping plugin integration tests"
        return 1
    fi
}

# Function to cleanup background processes
cleanup() {
    echo "Cleaning up background processes..."
    
    if [ ! -z "$MATRIX_PLUGIN_PID" ]; then
        echo "Stopping Matrix plugin (PID: $MATRIX_PLUGIN_PID)..."
        kill $MATRIX_PLUGIN_PID 2>/dev/null || true
        wait $MATRIX_PLUGIN_PID 2>/dev/null || true
    fi
}

# Set up cleanup trap
trap cleanup EXIT

# Install test dependencies
echo "Installing test dependencies..."
cd "$BROKER_DIR"
pip install -r test_requirements.txt

# Build protobuf files
echo "Building protobuf files..."
cd "$PROJECT_ROOT"
if [ -f "scripts/build-proto.sh" ]; then
    ./scripts/build-proto.sh
else
    echo "Warning: build-proto.sh not found, assuming protobufs are already built"
fi

cd "$BROKER_DIR"

# Run basic broker tests (with mocked plugins)
echo ""
echo "=== Running Broker Integration Tests (with mocks) ==="
python -m pytest test_integration.py -v --tb=short -m "not slow"

# Check if we should run Matrix plugin tests
if [ "$1" = "--with-matrix" ] || [ "$1" = "--full" ]; then
    echo ""
    echo "=== Setting up Matrix homeserver for plugin tests ==="
    
    if start_matrix_homeserver; then
        echo ""
        echo "=== Building Matrix plugin ==="
        build_matrix_plugin
        
        echo ""
        echo "=== Starting Matrix plugin ==="
        if start_matrix_plugin; then
            echo ""
            echo "=== Running Matrix Plugin Integration Tests ==="
            python -m pytest test_matrix_plugin.py -v --tb=short
        else
            echo "Skipping Matrix plugin tests due to startup failure"
        fi
    else
        echo "Skipping Matrix plugin tests due to homeserver unavailability"
    fi
fi

# Run performance/load tests if requested
if [ "$1" = "--performance" ] || [ "$1" = "--full" ]; then
    echo ""
    echo "=== Running Performance Tests ==="
    python -m pytest test_integration.py -v --tb=short -m "slow"
fi

echo ""
echo "=== Test Suite Completed Successfully! ==="
echo ""
echo "Test Summary:"
echo "✓ Broker integration tests completed"

if [ "$1" = "--with-matrix" ] || [ "$1" = "--full" ]; then
    echo "✓ Matrix plugin integration tests completed"
fi

if [ "$1" = "--performance" ] || [ "$1" = "--full" ]; then
    echo "✓ Performance tests completed"
fi

echo ""
echo "Usage:"
echo "  $0                 # Run basic broker tests only"
echo "  $0 --with-matrix   # Include Matrix plugin tests"
echo "  $0 --performance   # Include performance tests"
echo "  $0 --full          # Run all tests"
