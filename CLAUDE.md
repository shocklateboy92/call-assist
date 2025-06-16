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
- **Runtime state** stored in `runtime/` directory (gitignored) for easy debugging

## Next Steps
1. ✅ Design specific gRPC service definitions
2. ✅ Create project scaffolding
3. Implement broker capability detection logic
4. Build Matrix plugin with WebRTC support