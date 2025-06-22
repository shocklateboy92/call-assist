# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## General Instructions

When dealing with python code, follow the guidelines written in @.github/instructions/python.instructions.md

## Essential Development Commands

### Development Environment Setup

**Auto-setup**: The development environment is automatically set up during devcontainer creation by running `call-assist/scripts/setup-dev-env.sh`, which includes:
- Call Assist package installation in editable mode
- All Python dependencies (test, integration, broker)
- Protobuf file generation
- Node.js dependencies for Matrix plugin

**Manual setup** (for debugging or rebuilding):
```bash
cd call-assist
./scripts/setup-dev-env.sh         # Complete development environment setup
```

This enables clean imports without `sys.path` manipulations:
- `proto_gen.*` for protobuf generated code  
- `addon.broker.*` for broker functionality
- `integration.*` for Home Assistant integration
- `tests.*` for test utilities

### Protobuf Generation

Happens on devcontainer creation, but can be manually triggered if proto files change:

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
# Dependencies install automatically via devcontainer calling setup-dev-env.sh
# For manual reinstall or debugging:
cd call-assist && ./scripts/setup-dev-env.sh

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
   - Receives generic entities from broker (domain-agnostic)
   - Sends credentials to broker/plugins on startup

2. **Home Assistant Add-on** - Published on GitHub
   - **Broker**: Orchestrates plugins and exposes business-logic-driven entities
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
5. **Entity Architecture**: Broker-controlled, domain-agnostic entity system

### gRPC Service Definitions
**Completed**: Three core service contracts defined in `/proto/`

1. **broker_integration.proto** - HA Integration ↔ Broker communication
   - Configuration/credentials management
   - Call initiation/termination
   - **Generic entity management** (`GetEntities` RPC)
   - Real-time entity update streaming
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
   - **Generic entity update system** (`EntityUpdate` messages)

**Key Features:**
- **Business-logic-driven entity system**: Broker decides what entities to expose
- **Domain-agnostic integration**: Single entity type handles all use cases
- Bidirectional streaming for real-time events
- Capability negotiation system for direct/transcoding fallback
- Protocol-agnostic design for future extensibility
- Comprehensive call lifecycle management

### Entity Architecture Design

**Philosophy**: Push business logic to the broker for easier future updates, while keeping the integration thin and domain-agnostic.

**Implementation**:
```
Broker (Business Logic) → Generic Entities → HA Integration (Presentation)
```

**Entity Types** (defined by broker):
1. **Call Stations**: Camera + Media Player combinations for making calls
2. **Contacts**: Discovered contacts from protocol plugins (Matrix rooms, XMPP JIDs)
3. **Plugin Status**: Status of protocol plugins (Matrix, XMPP)
4. **Broker Status**: Overall system health and configuration

**Benefits**:
- ✅ **Future-proof**: Add new entity types without changing integration code
- ✅ **Broker-controlled**: Business logic updates don't require integration releases
- ✅ **Scalable**: Handles any number of cameras, media players, contacts automatically
- ✅ **Maintainable**: Clear separation between broker logic and HA presentation

**Key Changes**:
- Added `GetEntities` RPC that returns `EntityDefinition` objects
- Broker creates call stations from camera+media_player combinations
- Integration uses generic sensor platform for all entity types
- Real-time updates via `StreamEntityUpdates` for state changes

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

## Home Assistant Integration UI Enhancement Plan

### Current UI Implementation Status
- ✅ **Basic Config Flow**: Host/port validation and broker connectivity testing
- ✅ **Dynamic Options Flow**: Data-driven forms from broker schemas with protocol selection
- ✅ **Service-Based Account Management**: Add/update/remove accounts via HA services
- ❌ **User-Accessible Account Management**: No UI for viewing/managing added accounts

### Available Home Assistant UI Components
**Modern Selector Types** (36+ available):
- **Select/Multi-Select**: Dropdown menus with predefined options
- **Text Selectors**: Input fields with autocomplete, validation, and password masking
- **Device/Entity Selectors**: Choose from existing HA devices/entities
- **Boolean Selectors**: Toggle switches
- **Object Selectors**: YAML data input
- **Template Selectors**: Jinja2 template input

**Integration Patterns**:
- **Multi-Step Config Flows**: Sequential setup processes
- **Options Flows**: Runtime configuration accessible via Integrations → Configure
- **Device Registry**: Visual device management with status and actions
- **OAuth2 Scaffolding**: Centralized authentication handling

### Required UI Enhancements

#### 1. **Options Flow for Account Management**
Create accessible account management via Integrations → Configure:
```python
async def async_step_init(self, user_input=None):
    # Show account list with status
    
async def async_step_manage_account(self, user_input=None):
    # Edit/Remove specific account
    
async def async_step_add_account(self, user_input=None):
    # Add new account flow
```

#### 2. **Modernize with Selector System**
Replace voluptuous schemas with selector-based ones:
```python
DATA_SCHEMA = {
    "protocol": {"selector": {"select": {"options": ["matrix", "xmpp"]}}},
    "homeserver": {"selector": {"text": {"type": "url"}}},
    "username": {"selector": {"text": {"autocomplete": "username"}}},
    "password": {"selector": {"text": {"type": "password"}}}
}
```

#### 3. **Device Registry Integration**
- Register broker as device with accounts as sub-devices
- Provide device information (protocol, status, last seen)
- Enable device-level management actions

#### 4. **Enhanced Account Dashboard**
- **Account List**: Show all configured accounts with connection status
- **Status Indicators**: Real-time connection monitoring per account
- **Bulk Operations**: Add multiple accounts, test all connections
- **Error Recovery**: Reauthentication flows for expired credentials

### Implementation Priority
1. **High**: Options flow for account list and management
2. **Medium**: Modernize to selector-based schemas  
3. **Medium**: Device registry integration
4. **Low**: Advanced features (bulk operations, templates)

## Next Steps
1. ✅ Design specific gRPC service definitions
2. ✅ Create project scaffolding
3. ✅ Build Matrix plugin with WebRTC support
4. ✅ **Implement generic entity architecture** (domain-agnostic integration)
5. ✅ **Fix integration startup issues** (NoneType errors resolved)
6. 🔄 Implement real WebRTC peer connections in Matrix plugin
7. 🔄 **Implement account management UI enhancements**
8. Implement broker capability detection logic
9. Add configuration flow for camera/media player selection
10. Implement contact discovery from Matrix plugin