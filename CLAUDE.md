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
python -m pytest call-assist/tests
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
   - **Web UI**: Standalone account management interface (NiceGUI + FastAPI)
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
│   ├── broker/                         # Main orchestrator with web UI
│   │   ├── main.py                     # gRPC server + web UI server
│   │   ├── ludic_components.py         # Ludic web interface components
│   │   ├── ludic_views.py              # Ludic views for all UI
│   │   ├── web_api.py                  # FastAPI REST endpoints
│   │   ├── models.py                   # SQLModel database schemas
│   │   ├── database.py                 # SQLite database management
│   │   ├── queries.py                  # Database queries
│   │   ├── account_service.py          # Account business logic and status checking
│   │   ├── plugin_manager.py           # Plugin loading and management logic
│   │   ├── generate_plugin_schema.py   # generate JSON schema for plugin.yaml
│   │   ├── web_server.py               # FastAPI web server
│   ├── plugins/
│   │   ├── matrix/       # TypeScript
│   │   └── xmpp/         # C++
├── scripts/              # Build/development scripts
├── tests/                # Integration test, used for primary validation and development
├── proto/                # Shared gRPC schemas
├── Dockerfile            # Container build (moved to root for easy proto access)
├── pyproject.toml        # Python dependencies and configuration including tests
├── docker-compose.dev.yml # Development environment
└── .github/workflows/    # CI/CD for multi-language builds
```

### Technical Decisions Made
1. **Media Server**: GStreamer for real-time processing and format flexibility
2. **Camera Support**: RTSP streams + Home Assistant camera entities
3. **Media Player Support**: Chromecast primary, DLNA/UPnP/Miracast stretch goals
4. **WebRTC Integration**: Leverage Matrix's native WebRTC support for direct streaming
5. **Entity Architecture**: Broker-controlled, domain-agnostic entity system
7. **Form Generation**: Schema-driven dynamic forms for protocol-specific configuration

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

### Web UI Technology Stack

**Migration from NiceGUI to Ludic**: The project migrated from NiceGUI to Ludic for better testability and simpler HTML generation without client-side JavaScript dependencies.

**Ludic Framework**:
- **Documentation**: https://github.com/getludic/ludic
- **FastAPI Integration**: https://getludic.dev/docs/integrations#fastapi
- **Philosophy**: Type-guided HTML components in pure Python with minimal JavaScript
- **Benefits**: Server-side rendering, component reusability, type safety, easy testing via HTTP requests
- **Installation**: `pip install "ludic[fastapi]"`
- **Usage Pattern**: Return Ludic components directly from FastAPI endpoints

**andreasphil Design System**:
- **Repository**: https://github.com/andreasphil/design-system
- **Demo/Docs**: https://andreasphil.github.io/design-system/
- **Philosophy**: Small CSS framework (~6kb) that makes semantic HTML look good out-of-the-box
- **Components**: Buttons, forms, tables, dialogs, navigation, typography
- **Benefits**: No classes needed on semantic HTML, automatic responsive design, light/dark mode
- **Usage**: Include CSS file, use semantic HTML elements with optional component classes

**HTMX Integration**:
- **Purpose**: Provides interactivity without custom JavaScript
- **CDN**: Include HTMX via CDN in HTML head
- **Usage**: Add `hx-*` attributes to HTML elements for AJAX interactions
- **Benefits**: No JavaScript needed, server-side rendering, progressive enhancement
- **Pattern**: Use `hx-get`, `hx-post`, `hx-target`, `hx-swap` attributes on forms and buttons

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
  - **Web UI**: `http://localhost:8080/ui` - Account management interface
  - **REST API**: `http://localhost:8080/api/` - Programmatic access
  - **gRPC Server**: `localhost:50051` - Integration communication
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

## Account Management - Simplified Architecture

### Implementation Complete ✅
Simplified account management to **one account per integration instance**:

### **Architecture:**
```
Home Assistant Integration Instance = One Broker Connection + One Account
```

**Philosophy**: Users add multiple integration instances (via "Add Integration" button) rather than managing multiple accounts within a single integration instance.

### **Benefits:**
- ✅ **Familiar Pattern**: Matches standard HA integration patterns (multiple Plex servers, Hue bridges, etc.)
- ✅ **Simplified Code**: No complex device management or account coordination
- ✅ **Clear Separation**: Each account gets its own integration instance with isolated state
- ✅ **Easy Management**: Users can enable/disable individual accounts via HA's native integration controls
- ✅ **Scalable**: No limits on number of accounts - just add more integration instances

### **User Experience:**
1. **Add First Account**: Install integration → configure broker + first account
2. **Add More Accounts**: Click "Add Integration" → configure same broker + different account  
3. **Account Management**: Use HA's native integration management (enable/disable/remove per instance)
4. **Status Monitoring**: Each integration instance provides its own sensors for account status

### **Key Components:**

#### **1. Two-Step Config Flow** (`config_flow.py`)
- **Step 1**: Broker connection (host/port validation)
- **Step 2**: Account configuration (protocol, credentials)
- **Validation**: Tests both broker connectivity and account credentials during setup

#### **2. Coordinator** (`coordinator.py`)
- **Single Account**: Manages one account per integration instance
- **Auto-Push**: Pushes account credentials to broker on startup and reconnection
- **Streaming**: Handles real-time call and contact events for the account

#### **3. Config Entry Data Structure:**
```python
{
    "host": "localhost",
    "port": 50051,
    "protocol": "matrix",
    "account_id": "@user:matrix.org", 
    "display_name": "My Matrix Account",
    "credentials": {
        "homeserver": "https://matrix.org",
        "username": "user",
        "password": "secret"
    }
}
```

### **Migration from Device-Based Approach** ✅
- ✅ **Removed**: `device_manager.py`, `services.py`, `account_sensor.py`, `device_trigger.py`, `device_action.py`
- ✅ **Simplified**: Config flow, coordinator, and integration setup
- ✅ **Updated**: All tests to use one-account-per-instance pattern

## Standalone Web UI Architecture ✅

### **Implementation Complete**
Replaced Home Assistant-only UI limitations with a standalone web interface:

### **New Architecture:**
```
Broker (gRPC + Web Server) ↔ Home Assistant Integration (Simplified)
                           ↔ Web UI (Full Management)
```

**Philosophy**: Decouple account management from Home Assistant constraints while maintaining integration functionality.

### **Key Components:**

#### **1. SQLite Database** (`models.py`, `database.py`)
- **Account Storage**: Protocol credentials with encryption support
- **Settings Management**: Configurable broker behavior
- **Call History**: Persistent logging with metadata
- **Database Migration**: Seamless transition from in-memory storage

#### **2. FastAPI REST API** (`web_api.py`)
- **Account CRUD**: Full account lifecycle management
- **Settings API**: Runtime configuration updates
- **Call History**: Query and analytics endpoints
- **Health Monitoring**: System status and diagnostics

#### **3. NiceGUI Web Interface** (`web_ui.py`)
- **Account Dashboard**: Visual account management with status indicators
- **Dynamic Forms**: Protocol-specific configuration forms
- **Status Monitoring**: Real-time system health and statistics
- **Call History**: Searchable call logs with duration tracking

#### **4. Schema-Driven Forms** (`form_generator.py`)
- **Protocol Schemas**: Matrix and XMPP configuration templates
- **Dynamic Generation**: Automatic form creation from field definitions
- **Validation**: Type checking, required fields, URL validation
- **Extensibility**: Easy addition of new protocols

### **Benefits:**
- ✅ **No HA Limitations**: Full UI control without Home Assistant constraints
- ✅ **Persistent Storage**: SQLite database for configuration and history
- ✅ **Data-Driven**: Schema-based forms for easy protocol addition
- ✅ **RESTful API**: Programmatic access for automation
- ✅ **Server-Side Rendering**: Simple testing via HTTP requests
- ✅ **Standalone**: Independent of Home Assistant for management

### **Access Points:**
- **Web UI**: `http://localhost:8080/ui` - Complete management interface
- **REST API**: `http://localhost:8080/api/` - Programmatic access
- **API Docs**: `http://localhost:8080/docs` - Interactive documentation
- **gRPC Server**: `localhost:50051` - Home Assistant integration

### **Migration Impact:**
- **Database Persistence**: Automatic migration from in-memory account storage
- **HA Integration**: Simplified to focus on entity presentation only
- **Account Management**: Moved entirely to standalone web UI
- **Testing**: Comprehensive test suite for all web components

## Next Steps
1. ✅ Design specific gRPC service definitions
2. ✅ Create project scaffolding
3. ✅ Build Matrix plugin with WebRTC support
4. ✅ **Implement generic entity architecture** (domain-agnostic integration)
5. ✅ **Fix integration startup issues** (NoneType errors resolved)
6. ✅ **Simplify account management** (one account per integration instance)
7. ✅ **Implement standalone web UI** (NiceGUI + FastAPI + SQLite)
8. 🔄 Implement real WebRTC peer connections in Matrix plugin
9. Implement broker capability detection logic
10. Add configuration flow for camera/media player selection
11. Implement contact discovery from Matrix plugin