# Call Assist Architecture

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
   - **Web UI**: Standalone account management interface (Ludic + FastAPI)
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
/
├── call_assist/
│   ├── integration/           # Home Assistant custom integration (Python)
│   │   ├── config_flow.py     # Two-step configuration flow
│   │   ├── coordinator.py     # Single account per instance management
│   │   ├── sensor.py         # Generic entity sensor platform
│   │   └── proto_gen/        # Generated protobuf Python files
│   ├── addon/
│   │   ├── broker/           # Main orchestrator with web UI
│   │   │   ├── main.py       # gRPC server + FastAPI web server
│   │   │   ├── ludic_components.py  # Ludic web interface components
│   │   │   ├── ludic_views.py       # Ludic views for all UI routes
│   │   │   ├── models.py            # SQLModel database schemas
│   │   │   ├── database.py          # SQLite database management
│   │   │   ├── queries.py           # Database queries for all entities
│   │   │   ├── account_service.py   # Account business logic
│   │   │   ├── call_station_service.py  # Call station management
│   │   │   ├── plugin_manager.py    # Plugin loading and lifecycle
│   │   │   ├── generate_plugin_schema.py  # JSON schema generation
│   │   │   └── web_server.py        # FastAPI web server setup
│   │   ├── plugins/
│   │   │   ├── matrix/       # TypeScript - ✅ IMPLEMENTED with real WebRTC
│   │   │   │   ├── src/index.ts     # Full WebRTC implementation
│   │   │   │   ├── package.json     # Node.js dependencies
│   │   │   │   └── dist/           # Compiled TypeScript output
│   │   │   └── xmpp/         # C++ - ❌ NOT IMPLEMENTED (directory only)
│   ├── scripts/              # Build/development scripts
│   │   ├── setup-dev-env.sh  # Complete development environment setup
│   │   ├── build-proto.sh    # Protobuf generation with betterproto
│   │   ├── test-video-infrastructure.sh  # Video testing validation
│   │   └── restart-ha-for-testing.sh     # Development utility
│   ├── tests/                # Integration tests with video infrastructure
│   │   ├── conftest.py       # Test fixtures and broker setup
│   │   ├── fixtures/         # Mock Chromecast and test utilities
│   │   ├── test_matrix_plugin_e2e.py     # Matrix plugin end-to-end tests
│   │   ├── test_video_call_e2e.py        # Video call testing
│   │   └── test_matrix_webrtc_real.py    # Real WebRTC implementation tests
│   ├── proto/                # Shared gRPC schemas
│   ├── proto_gen/           # Generated Python protobuf files (betterproto)
│   ├── docs/                # Additional technical documentation
│   │   ├── DATA_DRIVEN_CONFIG.md         # Configuration architecture
│   │   ├── DEPENDENCY_INJECTION.md      # DI patterns
│   │   └── REAL_WEBRTC_IMPLEMENTATION.md # WebRTC implementation guide
│   ├── config/              # Development environment configuration
│   │   ├── coturn/          # TURN server configuration
│   │   ├── homeassistant/   # HA development instance config files
│   │   └── synapse/         # Matrix server configuration
│   ├── Dockerfile           # Container build
│   └── pyproject.toml       # Python dependencies and configuration
├── runtime/                 # Runtime state directory (gitignored). Ignore everything in here.
├── docker-compose.dev.yml   # Development environment with all services
└── .github/
    ├── instructions/        # Project coding instructions
    └── dependabot.yml      # Dependency management (no CI/CD workflows yet)
```

### Technical Decisions Made
1. **Media Server**: GStreamer for real-time processing and format flexibility
2. **Camera Support**: RTSP streams + Home Assistant camera entities
3. **Media Player Support**: Chromecast primary, DLNA/UPnP/Miracast stretch goals
4. **WebRTC Integration**: Leverage Matrix's native WebRTC support for direct streaming
5. **Entity Architecture**: Broker-controlled, domain-agnostic entity system
6. **Form Generation**: Schema-driven dynamic forms for protocol-specific configuration

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

**Complete Docker Compose Setup**: VS Code devcontainer with automatic service startup:

#### **Core Services**
- **devcontainer** - Development environment with Python/TypeScript/mypy support
- **homeassistant** - `http://localhost:8123` with integration auto-loaded
- **call_assist-addon** - Main broker service with:
  - **Web UI**: `http://localhost:8080/ui` - Complete management interface  
  - **REST API**: `http://localhost:8080/api/` - Programmatic access
  - **API Docs**: `http://localhost:8080/docs` - Interactive documentation
  - **gRPC Server**: `localhost:50051` - Home Assistant integration communication

#### **Testing Infrastructure**
- **synapse** - Matrix homeserver at `http://localhost:8008` for Matrix plugin testing
- **coturn** - TURN server on port 3478 for WebRTC NAT traversal
- **RTSP Test Servers** - Synthetic video streams at `rtsp://localhost:8554/test_camera_*`
- **Mock Chromecast** - HTTP server simulating Chromecast behavior for media player testing

#### **Development Tools**
- **Runtime State**: `runtime/` directory (gitignored) for debugging and data persistence
- **Auto-Setup**: `scripts/setup-dev-env.sh` runs automatically on devcontainer creation
- **Video Testing**: `scripts/test-video-infrastructure.sh` validates all media components
- **Type Safety**: Protobuf generation with betterproto and mypy type stubs

## Matrix Plugin WebRTC Implementation ✅

### Implementation Complete - Real WebRTC with @roamhq/wrtc
The Matrix plugin (`addon/plugins/matrix/src/index.ts`) features a production-ready WebRTC implementation:

#### **Core WebRTC Features Implemented ✅**
- ✅ **Real WebRTC Library**: Uses `@roamhq/wrtc` for native RTCPeerConnection support
- ✅ **Hybrid Implementation**: Mock WebRTC for development/testing + real WebRTC for production
- ✅ **Complete SDP Handling**: Real SDP offer/answer generation and exchange
- ✅ **ICE Candidate Management**: Full ICE gathering, exchange, and processing
- ✅ **Connection State Monitoring**: Real peer connection state tracking and events
- ✅ **Matrix VoIP Integration**: Full Matrix VoIP event support (invite, answer, hangup, candidates)
- ✅ **Media Pipeline Ready**: Architecture prepared for RTSP → WebRTC media integration
- ✅ **FFMPEG Integration**: Built-in FFMPEG support for media transcoding
- ✅ **Resource Management**: Proper cleanup and lifecycle management

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

#### **Production WebRTC Implementation**

**Implementation Status**: Production-ready with `@roamhq/wrtc` library

**Key Features**:
- Real RTCPeerConnection with native WebRTC support
- FFMPEG integration for media transcoding
- TURN/STUN server support via coturn
- Mock implementation for development/testing
- Comprehensive ICE candidate handling
- Matrix VoIP event integration

#### **Integration Points**
- **Matrix Signaling**: Complete Matrix VoIP event handling (`m.call.invite`, `m.call.answer`, `m.call.hangup`, `m.call.candidates`)
- **Broker Communication**: WebRTC call events streamed to broker via gRPC
- **TURN Server**: Ready for coturn integration (coturn:3478) for NAT traversal
- **Media Pipeline**: Architecture ready for RTSP → WebRTC media stream integration

#### **Testing Infrastructure**
- **End-to-End Tests**: Comprehensive test suite covering call lifecycle and WebRTC behavior
- **Mock Infrastructure**: RTSP test servers and mock Chromecast for complete video call testing
- **Integration Testing**: Broker entity streaming and call state management validation

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

#### **2. FastAPI REST API** (integrated into `web_server.py`)
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

#### **4. Schema-Driven Forms** (`generate_plugin_schema.py`)
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

### **Current System Capabilities**
- **Account Management**: Complete protocol account lifecycle via standalone web UI
- **Call Station Management**: Manual configuration of camera + media player combinations with database persistence
- **Matrix WebRTC**: Production-ready WebRTC implementation with real peer connections and media pipeline support
- **Protocol Integration**: Full Matrix VoIP support with signaling, ICE handling, and call state management
- **Entity Streaming**: Real-time broker entities synchronized with Home Assistant via gRPC
- **Status Monitoring**: Live availability tracking and comprehensive call state management
- **Web Interface**: Standalone management interface with FastAPI, Ludic, and HTMX
- **Testing Infrastructure**: Complete video call testing with RTSP streams, mock Chromecast, and WebRTC simulation
- **Database Persistence**: SQLite storage with automatic migrations for accounts, call stations, and settings

### **Next Development Priorities**
1. 🎥 **Media Pipeline Integration**: Connect RTSP camera streams to WebRTC media tracks (FFMPEG integration ready)
2. 📞 **Complete Call Functionality**: End-to-end calling through call stations with real media
3. 🔍 **Contact Discovery**: Matrix contact lists and presence management
4. ⚙️ **Broker Capabilities**: Dynamic capability detection and media negotiation
5. 📱 **XMPP Plugin**: C++ implementation for protocol validation
6. 🧪 **Advanced Integration Testing**: Full end-to-end call scenarios with real media streams
7. 🚀 **CI/CD Pipeline**: GitHub Actions workflows for automated testing and building
8. 📦 **Packaging**: HACS integration and Home Assistant Add-on publishing

### **Technical Debt & Improvement Areas**
- **XMPP Plugin**: Complete C++ implementation to match Matrix plugin capabilities
- **CI/CD Pipeline**: Add GitHub Actions workflows for automated testing and multi-language builds
- **Type Errors**: Resolve remaining Ludic component type warnings
- **Error Handling**: Improve exception handling in web UI routes and plugin management
- **Performance**: Optimize entity update streaming and database queries
- **Media Pipeline**: Complete RTSP → WebRTC media stream integration
- **Documentation**: Add inline code documentation and API examples