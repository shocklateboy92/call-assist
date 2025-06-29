# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## General Instructions

When dealing with python code, follow the guidelines written in @.github/instructions/python.instructions.md

## Essential Development Commands

## Type checking

We use mypy for type checking. To run type checks, use:

```bash
cd call_assist
mypy --explicit-package-bases . # or you can specify a specific file path here
```

Do that after making any changes to the python code.

### Development Environment Setup

**Auto-setup**: The development environment is automatically set up during devcontainer creation by running `call_assist/scripts/setup-dev-env.sh`, which includes:
- Call Assist package installation in editable mode
- All Python dependencies (test, integration)
- Protobuf file generation
- Node.js dependencies for Matrix plugin

**Manual setup** (for debugging or rebuilding):
```bash
./call_assist/scripts/setup-dev-env.sh         # Complete development environment setup
```

This enables clean imports without `sys.path` manipulations:
- `proto_gen.*` for protobuf generated code  
- `addon.broker.*` for broker functionality
- `integration.*` for Home Assistant integration
- `tests.*` for test utilities

### Protobuf Generation

Happens on devcontainer creation, but can be manually triggered if proto files change:

```bash
# Must run after proto file changes - generates Python files using betterproto
./call_assist/scripts/build-proto.sh
```

### Broker Development (Python)
```bash
./call_assist/run_broker.sh                    # Starts the broker after type checking and linting
python -m pytest call_assist/tests/ -xvs      # Run all integration tests
python -m pytest call_assist/tests/test_matrix_plugin_e2e.py -xvs  # Run Matrix plugin tests

# Web UI accessible at http://localhost:8080/ui
# Features: Account management, Call Station configuration, Status monitoring
```

### Matrix Plugin Development (TypeScript)
```bash
cd call_assist/addon/plugins/matrix
npm run build           # Compile TypeScript
# Plugin is run via integration tests, not directly
```

### Development Environment
```bash
# Dependencies install automatically via devcontainer calling setup-dev-env.sh
# For manual reinstall or debugging:
cd call_assist && ./scripts/setup-dev-env.sh

# Services start automatically via devcontainer.json
# To restart or interact with services at runtime, use docker commands:
docker-compose -f docker-compose.dev.yml restart <service-name>

# Services available at:
# - Home Assistant: http://localhost:8123
# - Matrix Synapse: http://localhost:8008
# - TURN Server: coturn:3478
# - RTSP Test Server: rtsp://localhost:8554 (with test cameras)
# - Mock Chromecast: http://localhost:8008 (for testing)
```

### Testing Guidelines

- Generally, prefer integration tests over unit tests for this project
- Use the `call_assist/tests/` directory for all test files
- There are fixtures available in `tests/conftest.py` to instantiate and give a running broker

### Video Testing Infrastructure

**Auto-Start Video Services**: The development environment automatically starts video testing infrastructure:

```bash
# Test video infrastructure health
call_assist/scripts/test-video-infrastructure.sh

# Run video-specific tests
python -m pytest call_assist/tests/test_video_call_e2e.py -xvs          # End-to-end video call tests
python -m pytest call_assist/tests/test_broker_integration.py::test_rtsp_stream_integration -xvs

# Available test streams
# - rtsp://localhost:8554/test_camera_1 (SMPTE color bars, 640x480@10fps)
# - rtsp://localhost:8554/test_camera_2 (Test pattern, 640x480@10fps)
```

**Video Test Components**:
- **RTSP Server**: `aler9/rtsp-simple-server` with synthetic video streams
- **Mock Chromecast**: HTTP server simulating Chromecast behavior for media player testing
- **Test Fixtures**: Camera and media player entities with RTSP streams in `conftest.py`
- **Resource Efficient**: Lightweight 480p@10fps streams optimized for devcontainer usage

## Architecture

For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).
