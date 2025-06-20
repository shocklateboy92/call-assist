
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## General Instructions

When dealing with python code, follow the guidelines written in @.github/instructions/python.instructions.md

## Essential Development Commands

### Protobuf Generation
```bash
# Must run after proto file changes - generates Python, TypeScript, and C++ files
./scripts/build-proto.sh
```

### Broker Development (Python)
```bash
cd call-assist/addon/broker
./dev.sh                           # Start broker in development mode
./run_all_tests.sh                 # Run basic integration tests
./run_all_tests.sh --with-matrix   # Include Matrix plugin tests (builds and runs plugin)
./run_all_tests.sh --full          # Run all tests including performance
python -m pytest test_integration.py -v  # Run specific integration tests
```

### Matrix Plugin Development (TypeScript)
```bash
cd call-assist/addon/plugins/matrix
npm run proto           # Generate protobuf files
npm run build           # Compile TypeScript
# Plugin is run via integration tests in call-assist/addon/broker/test_matrix_plugin.py, not directly
```

### Development Environment
```bash
# Dependencies install automatically via devcontainer postCreateCommand
# To manually reinstall dependencies:
./scripts/setup-dev-env.sh

# Services start automatically via devcontainer.json
# To restart or interact with services at runtime, use sudo:
sudo docker-compose -f docker-compose.dev.yml restart <service-name>

# Services available at:
# - Home Assistant: http://homeassistant:8123
# - Matrix Synapse: http://synapse:8008
# - TURN Server: coturn:3478
```


# Call Assist Project Plan

## Overview
Call Assist: Like Music Assistant, but for making video calls. Tightly integrated with Home Assistant from the start. Allows users to choose a Home Assistant camera entity and media player entity (that supports casting) to make arbitrary video calls.

## Project Architecture

### Core Components
1. **Home Assistant Custom Integration** (Python) - Published to HACS
   - Handles user interaction/configuration
   - Manages authentication credentials
   - Sends credentials to broker/plugins on startup

2. **Home Assistant Add-on** - Published on GitHub
   - **Broker**: Orchestrates plugins and communication with HA integration
   - **Matrix Plugin**: NodeJS/TypeScript using matrix-js-sdk
   - **XMPP Plugin**: C++ using QXMPP library

### Communication Protocol
**Decision: gRPC + Protocol Buffers**
- Real-time bidirectional streaming for call events
- Strong type safety across Python, TypeScript, and C++
- Native support in all target languages
- Perfect for capability negotiation in streaming pipeline

### Audio/Video Pipeline Management

**Hybrid Architecture Approach:**
```
Camera (RTSP) → Broker (Capability Detection) → Call Plugin (Matrix/XMPP) → Media Player (Chromecast)
```

**Strategy:**
1. **Capability Detection Phase**: Broker queries formats/codecs from all components
2. **Fallback Logic**:
   - Direct WebRTC streaming when formats align (minimal resources)
   - GPU-accelerated transcoding when available (P600 support)
   - Software fallback or quality reduction for Raspberry Pi
3. **WebRTC-First**: Matrix uses WebRTC natively, RTSP→WebRTC bridge when needed

**Benefits:**
- Raspberry Pi users get efficient direct streaming
- Powerful servers can handle complex transcoding
- Graceful degradation vs failure

### Repository Structure (Monorepo)
```
call-assist/
├── integration/           # Home Assistant custom integration (Python)
├── addon/
│   ├── broker/           # Main orchestrator 
│   ├── plugins/
│   │   ├── matrix/       # TypeScript
│   │   └── xmpp/         # C++
├── proto/                # Shared gRPC schemas
├── Dockerfile            # Container build (moved to root for easy proto access)
├── docker-compose.dev.yml # Development environment
├── scripts/              # Build/development scripts
└── .github/workflows/    # CI/CD for multi-language builds
```

### Technical Decisions Made
1. **Media Server**: GStreamer for real-time processing and format flexibility
2. **Camera Support**: RTSP streams + Home Assistant camera entities
3. **Media Player Support**: Chromecast primary, DLNA/UPnP/Miracast stretch goals
4. **WebRTC Integration**: Leverage Matrix's native WebRTC support for direct streaming

### gRPC Service Definitions
**Completed**: Three core service contracts defined in `/proto/`

1. **broker_integration.proto** - HA Integration ↔ Broker communication
   - Configuration/credentials management
   - Call initiation/termination
   - Real-time status streaming
   - System capability queries

2. **call_plugin.proto** - Broker ↔ Call Plugin communication
   - Plugin lifecycle management
   - Call operations (start/accept/end)
   - Media negotiation for hybrid streaming approach
   - Real-time call event streaming

3. **common.proto** - Shared types and enums
   - Media capabilities and negotiation
   - Call states and events
   - Health status monitoring

**Key Features:**
- Bidirectional streaming for real-time events
- Capability negotiation system for direct/transcoding fallback
- Protocol-agnostic design for future extensibility
- Comprehensive call lifecycle management

### Development Environment
**Docker Compose Setup**: VS Code dev container automatically starts all services:
- **devcontainer** - Development environment with Python/TypeScript support
- **homeassistant** - Available at `localhost:8123` with integration mounted
- **call-assist-addon** - Broker and plugins running, accessible via service name
- **synapse** - Matrix homeserver at `localhost:8008` for testing Matrix plugin
- **coturn** - TURN server on port 3478 for WebRTC relay support
- **Runtime state** stored in `runtime/` directory (gitignored) for easy debugging

**Type Safety**: Protobuf files use mypy-protobuf for full type checking support:
- `.pyi` stub files are tracked in git for immediate IDE support
- Run `scripts/build-proto.sh` to regenerate protobuf files and type stubs
- Python protobuf files (`*_pb2.py`, `*_pb2_grpc.py`) are gitignored as generated files

## Matrix Plugin WebRTC Implementation Plan

### Current Status
The Matrix plugin (`addon/plugins/matrix/src/index.ts`) currently:
- ✅ Implements proper Matrix signaling (`m.call.invite`, `m.call.answer`, `m.call.hangup`)
- ✅ Handles Matrix room management and event processing
- ❌ Uses mock SDP generation instead of real WebRTC peer connections

### Required Changes for Real WebRTC

#### High Priority Tasks:
1. **Add WebRTC Library Dependency**
   - Install `wrtc` or `node-webrtc` package for Node.js WebRTC support
   - Update `package.json` dependencies

2. **RTCPeerConnection Management**
   - Create `RTCPeerConnection` instances per call ID
   - Manage peer connection lifecycle (create, configure, cleanup)
   - Track connection states and handle state changes

3. **Real Offer Generation** 
   - Replace `generateMockWebRTCOffer()` (line 455) with `RTCPeerConnection.createOffer()`
   - Use actual SDP from peer connection instead of hardcoded strings

4. **Answer Processing**
   - Replace `generateMockWebRTCAnswer()` (line 512) with proper `setRemoteDescription()`
   - Handle remote SDP offers in `handleIncomingCallInvite()`

5. **ICE Candidate Handling**
   - Collect ICE candidates from `RTCPeerConnection.onicecandidate`
   - Send candidates via Matrix `m.call.candidates` events
   - Process incoming ICE candidates in `handleIceCandidates()` (line 607)

#### Medium Priority Tasks:
6. **Media Stream Integration**
   - Connect Home Assistant camera feeds to WebRTC peer connections
   - Bridge RTSP streams to WebRTC media tracks
   - Handle audio/video track management

7. **Connection State Monitoring**
   - Monitor `RTCPeerConnection.connectionState`
   - Handle connection failures and reconnection logic
   - Emit appropriate call events for state changes

8. **STUN/TURN Configuration**
   - Configure ICE servers using coturn (already available on port 3478)
   - Add fallback STUN servers for NAT traversal
   - Handle ICE connection failures

#### Low Priority Tasks:
9. **Cleanup Mock Methods**
   - Remove `generateMockWebRTCOffer()` and `generateMockWebRTCAnswer()`
   - Remove `generateFingerprint()` helper

### Key Files to Modify:
- `addon/plugins/matrix/package.json` - Add WebRTC dependencies
- `addon/plugins/matrix/src/index.ts:144-147` - Real offer in `startCall()`
- `addon/plugins/matrix/src/index.ts:222-226` - Real answer in `acceptCall()`
- `addon/plugins/matrix/src/index.ts:455-516` - Remove mock SDP methods
- `addon/plugins/matrix/src/index.ts:607-616` - Process ICE candidates

### Integration Points:
- WebRTC peer connections need media input from broker's camera feed
- Matrix signaling layer is already functional and doesn't need changes
- TURN server configuration should use existing coturn service

## Next Steps
1. ✅ Design specific gRPC service definitions
2. ✅ Create project scaffolding
3. ✅ Build Matrix plugin with WebRTC support
4. 🔄 Implement real WebRTC peer connections in Matrix plugin
5. Implement broker capability detection logic