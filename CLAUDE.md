# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## General Instructions

When dealing with python code, follow the guidelines written in @.github/instructions/python.instructions.md

## Essential Development Commands

### Development Environment Setup

**Auto-setup**: The development environment is automatically set up during devcontainer creation by running `call_assist/scripts/setup-dev-env.sh`, which includes:
- Call Assist package installation in editable mode
- All Python dependencies (test, integration, broker)
- Protobuf file generation
- Node.js dependencies for Matrix plugin

**Manual setup** (for debugging or rebuilding):
```bash
cd call_assist
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
cd call_assist/addon/broker
python -m addon.broker.main                    # Start broker directly
python -m pytest tests/ -xvs                   # Run all integration tests
python -m pytest tests/test_matrix_plugin_e2e.py -xvs  # Run Matrix plugin tests

# Web UI accessible at http://localhost:8080/ui
# Features: Account management, Call Station configuration, Status monitoring
```

### Matrix Plugin Development (TypeScript)
```bash
cd call_assist/addon/plugins/matrix
npm run proto           # Generate protobuf files
npm run build           # Compile TypeScript
# Plugin is run via integration tests in call_assist/addon/broker/test_matrix_plugin.py, not directly
```

### Development Environment
```bash
# Dependencies install automatically via devcontainer calling setup-dev-env.sh
# For manual reinstall or debugging:
cd call_assist && ./scripts/setup-dev-env.sh

# Services start automatically via devcontainer.json
# To restart or interact with services at runtime, use sudo:
sudo docker-compose -f docker-compose.dev.yml restart <service-name>

# Services available at:
# - Home Assistant: http://homeassistant:8123
# - Matrix Synapse: http://synapse:8008
# - TURN Server: coturn:3478
# - RTSP Test Server: rtsp://rtsp-server:8554 (with test cameras)
# - Mock Chromecast: http://mock-chromecast:8008 (for testing)
```

### Testing Guidelines

- Generally, prefer integration tests over unit tests for this project
- Use the `tests/` directory for all test files
- There are fixtures available in `tests/conftest.py` to instantiate and give a running broker

### Video Testing Infrastructure

**Auto-Start Video Services**: The development environment automatically starts video testing infrastructure:

```bash
# Test video infrastructure health
call_assist/scripts/test-video-infrastructure.sh

# Run video-specific tests
python -m pytest tests/test_video_call_e2e.py -xvs          # End-to-end video call tests
python -m pytest tests/test_video_performance.py -xvs      # Performance and load testing
python -m pytest tests/test_broker_integration.py::test_rtsp_stream_integration -xvs

# Available test streams
# - rtsp://localhost:8554/test_camera_1 (SMPTE color bars, 640x480@10fps)
# - rtsp://localhost:8554/test_camera_2 (Test pattern, 640x480@10fps)
```

**Video Test Components**:
- **RTSP Server**: `aler9/rtsp-simple-server` with synthetic video streams
- **Mock Chromecast**: HTTP server simulating Chromecast behavior for media player testing
- **Test Fixtures**: Camera and media player entities with RTSP streams in `conftest.py`
- **Performance Tests**: Concurrent connections, state transitions, WebSocket load testing
- **Resource Efficient**: Lightweight 480p@10fps streams optimized for devcontainer usage


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
call_assist/
├── integration/           # Home Assistant custom integration (Python)
├── addon/
│   ├── broker/                         # Main orchestrator with web UI
│   │   ├── main.py                     # gRPC server + web UI server
│   │   ├── ludic_components.py         # Ludic web interface components
│   │   ├── ludic_views.py              # Ludic views for all UI
│   │   ├── web_api.py                  # FastAPI REST endpoints
│   │   ├── models.py                   # SQLModel database schemas (Account, CallStation, etc.)
│   │   ├── database.py                 # SQLite database management
│   │   ├── queries.py                  # Database queries for all entities
│   │   ├── account_service.py          # Account business logic and status checking
│   │   ├── call_station_service.py     # Call station business logic and validation
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
- **call_assist-addon** - Broker and plugins running, accessible via service name
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

## Matrix Plugin WebRTC Implementation ✅

### Implementation Complete
The Matrix plugin (`addon/plugins/matrix/src/index.ts`) now features a comprehensive WebRTC implementation:

#### **Core WebRTC Features Implemented ✅**
- ✅ **Real RTCPeerConnection Management**: Factory pattern with `createPeerConnection()` for easy mock/real switching
- ✅ **Proper SDP Offer/Answer Exchange**: Uses `createOffer()` and `createAnswer()` instead of mock generation
- ✅ **ICE Candidate Handling**: Collects, sends, and processes ICE candidates via Matrix signaling
- ✅ **Connection State Monitoring**: Tracks peer connection states and emits appropriate call events
- ✅ **Matrix Integration**: Enhanced Matrix signaling with real WebRTC session management
- ✅ **Resource Management**: Proper peer connection cleanup on call end and plugin shutdown

#### **Architecture Overview**
```typescript
// WebRTC Peer Connection Lifecycle
MatrixPlugin.startCall() → createPeerConnection() → createOffer() → Matrix signaling
                                ↓
Matrix events → handleCallAnswer() → setRemoteDescription() → ICE gathering
                                ↓
ICE candidates → Matrix m.call.candidates → handleIceCandidates() → addIceCandidate()
                                ↓
Connection established → onconnectionstatechange → Call active
```

#### **Key Implementation Details**

**1. Mock WebRTC Implementation** (`MockRTCPeerConnection`)
- **Purpose**: Enables development and testing without native WebRTC dependencies
- **Features**: Simulates real WebRTC behavior including SDP generation, ICE candidates, and state transitions
- **Production Ready**: Can be easily replaced with real WebRTC library (`wrtc` package)

**2. Enhanced Call Management**
```typescript
interface CallInfo {
  roomId: string;
  startTime: number;
  state: CallState;
  remoteStreamUrl?: string;
  peerConnection?: RTCPeerConnectionInterface;  // ✅ NEW: Real peer connection
  iceCandidates: RTCIceCandidateInit[];         // ✅ NEW: ICE candidate storage
}
```

**3. Real-time Event Integration**
- **Connection State Events**: Updates call states based on WebRTC connection status
- **ICE Candidate Exchange**: Automatic ICE candidate relay via Matrix `m.call.candidates` events
- **Matrix Signaling**: Enhanced offer/answer processing with proper SDP handling

#### **Ready for Production WebRTC**

**Current State**: Fully functional with mock WebRTC implementation
**Production Upgrade Path**:
1. Add `wrtc` dependency: `npm install wrtc`
2. Update `createPeerConnection()` factory:
```typescript
import * as wrtc from 'wrtc';

function createPeerConnection(): RTCPeerConnectionInterface {
  return new wrtc.RTCPeerConnection({
    iceServers: [
      { urls: 'stun:coturn:3478' },
      { urls: 'turn:coturn:3478', username: 'user', credential: 'pass' }
    ]
  });
}
```

#### **Integration Points**
- **Matrix Signaling**: Complete Matrix VoIP event handling (`m.call.invite`, `m.call.answer`, `m.call.hangup`, `m.call.candidates`)
- **Broker Communication**: WebRTC call events streamed to broker via gRPC
- **TURN Server**: Ready for coturn integration (coturn:3478) for NAT traversal
- **Media Pipeline**: Architecture ready for RTSP → WebRTC media stream integration

#### **Testing Infrastructure**
- **End-to-End Tests**: Comprehensive test suite covering call lifecycle and WebRTC behavior
- **Mock Infrastructure**: RTSP test servers and mock Chromecast for complete video call testing
- **Integration Testing**: Broker entity streaming and call state management validation

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

#### **3. Ludic Web Interface** (`ludic_components.py`, `ludic_views.py`)
- **Account Dashboard**: Visual account management with status indicators
- **Call Station Dashboard**: Manual configuration of camera + media player combinations
- **Dynamic Forms**: Protocol-specific configuration forms and entity selection dropdowns
- **Status Monitoring**: Real-time system health and availability tracking
- **Call History**: Searchable call logs with duration tracking
- **HTMX Integration**: Interactive UI updates without page refreshes

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
  - **Accounts**: `http://localhost:8080/ui` - Protocol account management
  - **Call Stations**: `http://localhost:8080/ui/call-stations` - Camera + media player configuration
  - **Status**: `http://localhost:8080/ui/status` - System health monitoring
  - **History**: `http://localhost:8080/ui/history` - Call logs and analytics
  - **Settings**: `http://localhost:8080/ui/settings` - Broker configuration
- **REST API**: `http://localhost:8080/api/` - Programmatic access
- **API Docs**: `http://localhost:8080/docs` - Interactive documentation
- **gRPC Server**: `localhost:50051` - Home Assistant integration

### **Migration Impact:**
- **Database Persistence**: Automatic migration from in-memory account storage
- **HA Integration**: Simplified to focus on entity presentation only
- **Account Management**: Moved entirely to standalone web UI
- **Testing**: Comprehensive test suite for all web components

## Call Station Management System ✅

### **Implementation Complete**
Implemented a comprehensive Call Station management system following the same architectural pattern as account management.

### **Migration from Auto-Generation:**
**Before**: Call stations were automatically created for every camera + media player combination
**After**: Call stations are manually configured by users, stored in database, and loaded on startup

### **New Architecture:**
```
Database-Driven Call Stations ↔ Broker Entity Updates ↔ Home Assistant Integration
                              ↔ Web UI Management Interface
```

**Philosophy**: Give users full control over call station configurations while maintaining real-time status monitoring.

### **Integration Impact:**
- **Home Assistant**: Receives call stations as broker entities with availability status
- **Broker**: Loads enabled stations on startup and monitors entity changes
- **Web UI**: Provides complete management interface independent of Home Assistant
- **Database**: Automatic table creation and migration support

## Implementation Status & Roadmap

### **Completed Features ✅**
1. ✅ **Project Scaffolding**: Complete development environment setup
2. ✅ **gRPC Service Definitions**: Protocol buffer contracts for all components
3. ✅ **Matrix Plugin WebRTC**: Complete peer connection implementation with real SDP and ICE handling
4. ✅ **Generic Entity Architecture**: Domain-agnostic Home Assistant integration
5. ✅ **Integration Startup**: Resolved NoneType errors and connection issues
6. ✅ **Account Management**: One account per integration instance pattern
7. ✅ **Standalone Web UI**: FastAPI + Ludic + SQLite management interface
8. ✅ **Call Station Management**: Manual configuration system with real-time status
9. ✅ **Video Testing Infrastructure**: Comprehensive RTSP + Chromecast testing framework
10. ✅ **End-to-End Testing**: Matrix call test infrastructure with broker integration

### **Architecture Achievements**
- **Clean Separation**: Broker handles business logic, HA handles presentation
- **Type Safety**: Strong typing throughout with Protocol Buffers and TypeScript
- **WebRTC Foundation**: Complete peer connection infrastructure with mock and real implementation paths
- **Dependency Injection**: Consistent pattern across all components
- **Database Persistence**: SQLite with automatic migrations
- **Real-Time Updates**: Live status monitoring and entity streaming
- **User Control**: Manual configuration for both accounts and call stations
- **Comprehensive Testing**: End-to-end video call testing with RTSP streams and mock devices

### **Current Capabilities**
- **Account Management**: Add/edit/delete protocol accounts via web UI
- **Call Station Management**: Configure camera + media player combinations
- **Matrix WebRTC**: Complete peer connection implementation with SDP offer/answer and ICE candidate handling
- **Protocol Support**: Matrix integration with real WebRTC signaling infrastructure
- **Status Monitoring**: Real-time availability tracking and call state management
- **Entity Streaming**: Broker entities appear in Home Assistant
- **Web Interface**: Complete management without Home Assistant limitations
- **Video Testing**: End-to-end testing with synthetic RTSP streams and mock Chromecast devices
- **Call Testing**: Matrix call lifecycle testing with WebRTC peer connection simulation
- **Performance Validation**: Load testing for concurrent connections and state transitions

### **Next Development Priorities**
1. 🎥 **Media Pipeline Integration**: Connect RTSP camera streams to WebRTC media tracks
2. 📞 **Complete Call Functionality**: End-to-end calling through call stations with real media
3. 🔌 **Production WebRTC**: Replace mock implementation with real `wrtc` library 
4. 🔍 **Contact Discovery**: Matrix contact lists and presence
5. ⚙️ **Broker Capabilities**: Dynamic capability detection and negotiation
6. 📱 **XMPP Plugin**: Second protocol implementation for validation
7. 🧪 **Integration Testing**: Full end-to-end call scenarios with real media streams
8. 📦 **Packaging**: HACS integration and Home Assistant Add-on publishing

### **Technical Debt**
- **Type Errors**: Resolve remaining Ludic component type warnings
- **Error Handling**: Improve exception handling in web UI routes
- **Performance**: Optimize entity update streaming
- **Documentation**: Add inline code documentation and examples
