# Call Assist

Like Music Assistant, but for making video calls. Tightly integrated with Home Assistant from the start.

## Architecture

- **Home Assistant Integration** (`integration/`) - Custom integration for HACS
- **Home Assistant Add-on** (`addon/`) - Docker container with broker and plugins
- **gRPC Protocol Definitions** (`proto/`) - Shared schemas for inter-service communication

## Development

See individual component READMEs for setup instructions:
- [Integration](integration/README.md)
- [Add-on](addon/README.md)

## Communication Flow

```
Home Assistant Integration ←→ Broker ←→ Call Plugins (Matrix/XMPP)
                                ↓
                           Media Pipeline
                                ↓
                        Camera ←→ Media Player
```