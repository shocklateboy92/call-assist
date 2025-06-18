#!/usr/bin/env node

import { createServer, createChannel, createClientFactory } from 'nice-grpc';
import { MatrixClient, createClient, MsgType, ClientEvent, RoomEvent } from 'matrix-js-sdk';
import { promises as fs } from 'fs';
import path from 'path';
import { Observable, Subject } from 'rxjs';

// Import generated protobuf types
import {
  CallPluginDefinition,
  CallPluginServiceImplementation,
  PluginConfig,
  PluginStatus,
  CallStartRequest,
  CallStartResponse,
  CallAcceptRequest,
  CallAcceptResponse,
  CallEndRequest,
  CallEndResponse,
  MediaNegotiationRequest,
  ServerStreamingMethodResult
} from './proto_gen/call_plugin';
import {
  CallState,
  CallEvent,
  CallEventType,
  MediaCapabilities,
  MediaNegotiation,
  HealthStatus
} from './proto_gen/common';
import { Empty } from './proto_gen/google/protobuf/empty';
import type { CallContext } from 'nice-grpc-common';

// Matrix plugin configuration interface
interface MatrixConfig {
  homeserver: string;
  accessToken: string;
  userId: string;
}

// Strongly typed call info interface
interface CallInfo {
  roomId: string;
  startTime: number;
  state: CallState;
  remoteStreamUrl?: string;
}

class MatrixCallPlugin {
  private matrixClient: MatrixClient | null = null;
  private server: ReturnType<typeof createServer> | null = null;
  private config: MatrixConfig | null = null;
  private activeWebRTCCalls: Map<string, CallInfo> = new Map();
  private callEventSubject: Subject<CallEvent> = new Subject();

  constructor() {
    console.log('Matrix Call Plugin initializing...');
  }

  async initialize(): Promise<void> {
    console.log('Starting Matrix Call Plugin...');
    
    // Start gRPC server to communicate with broker
    await this.startGrpcServer();
    
    console.log('Matrix Call Plugin started successfully');
  }

  private async startGrpcServer(): Promise<void> {
    const server = createServer();
    
    // Implement CallPlugin service
    const callPluginService: CallPluginServiceImplementation = {
      // Initialize plugin with credentials
      initialize: async (request: PluginConfig, context: CallContext): Promise<PluginStatus> => {
        console.log('Received initialize request:', request);
        
        try {
          this.config = {
            homeserver: request.credentials.homeserver || 'https://matrix.org',
            accessToken: request.credentials.access_token,
            userId: request.credentials.user_id
          };
          
          // Initialize Matrix client
          await this.initializeMatrixClient();
          
          return {
            initialized: true,
            authenticated: true,
            message: 'Matrix plugin initialized successfully',
            capabilities: {
              videoCodecs: ['VP8', 'VP9', 'H264'],
              audioCodecs: ['OPUS', 'G722'],
              supportedResolutions: [
                { width: 1280, height: 720, framerate: 30 },
                { width: 1920, height: 1080, framerate: 30 }
              ],
              hardwareAcceleration: false,
              webrtcSupport: true,
              maxBandwidthKbps: 2000
            }
          };
        } catch (error) {
          console.error('Matrix plugin initialization failed:', error);
          return {
            initialized: false,
            authenticated: false,
            message: `Initialization failed: ${error}`,
            capabilities: undefined
          };
        }
      },

      // Shutdown plugin
      shutdown: async (request: Empty, context: CallContext): Promise<Empty> => {
        console.log('Received shutdown request');
        await this.shutdown();
        return {};
      },

      // Start a call
      startCall: async (request: CallStartRequest, context: CallContext): Promise<CallStartResponse> => {
        console.log('Received start call request:', request);
        
        if (!this.matrixClient || !this.config) {
          return {
            success: false,
            message: 'Matrix client not initialized',
            state: CallState.CALL_STATE_FAILED,
            remoteStreamUrl: ''
          };
        }

        try {
          // Parse Matrix room ID or user ID from target address
          const roomId = request.targetAddress;
          const callId = request.callId;
          
          // Send a message to the room indicating call attempt
          await this.matrixClient.sendMessage(roomId, {
            msgtype: MsgType.Text,
            body: `📞 Incoming video call from ${this.config.userId} (Call ID: ${callId})`
          });
          
          // Store call information
          this.activeWebRTCCalls.set(callId, {
            roomId,
            startTime: Date.now(),
            state: CallState.CALL_STATE_INITIATING,
            remoteStreamUrl: `matrix://webrtc/${callId}`
          });
          
          // Emit call event
          this.callEventSubject.next({
            type: CallEventType.CALL_EVENT_INITIATED,
            timestamp: new Date(),
            callId,
            state: CallState.CALL_STATE_INITIATING,
            metadata: { roomId }
          });
          
          return {
            success: true,
            message: 'Call initiated successfully',
            state: CallState.CALL_STATE_INITIATING,
            remoteStreamUrl: `matrix://webrtc/${callId}`
          };
          
        } catch (error) {
          console.error('Failed to start Matrix call:', error);
          return {
            success: false,
            message: `Call failed: ${error}`,
            state: CallState.CALL_STATE_FAILED,
            remoteStreamUrl: ''
          };
        }
      },

      // Accept a call
      acceptCall: async (request: CallAcceptRequest, context: CallContext): Promise<CallAcceptResponse> => {
        console.log('Received accept call request:', request);
        
        const callId = request.callId;
        const callInfo = this.activeWebRTCCalls.get(callId);
        
        if (!callInfo) {
          return {
            success: false,
            message: 'Call not found',
            remoteStreamUrl: ''
          };
        }

        try {
          // Update call state
          callInfo.state = CallState.CALL_STATE_ACTIVE;
          callInfo.remoteStreamUrl = `matrix://webrtc/${callId}/accepted`;
          this.activeWebRTCCalls.set(callId, callInfo);
          
          // Emit call event
          this.callEventSubject.next({
            type: CallEventType.CALL_EVENT_ANSWERED,
            timestamp: new Date(),
            callId,
            state: CallState.CALL_STATE_ACTIVE,
            metadata: { roomId: callInfo.roomId }
          });
          
          return {
            success: true,
            message: 'Call accepted successfully',
            remoteStreamUrl: callInfo.remoteStreamUrl || ''
          };
        } catch (error) {
          console.error('Failed to accept Matrix call:', error);
          return {
            success: false,
            message: `Failed to accept call: ${error}`,
            remoteStreamUrl: ''
          };
        }
      },

      // End a call
      endCall: async (request: CallEndRequest, context: CallContext): Promise<CallEndResponse> => {
        console.log('Received end call request:', request);
        
        const callId = request.callId;
        const callInfo = this.activeWebRTCCalls.get(callId);
        
        if (!callInfo) {
          return {
            success: false,
            message: 'Call not found'
          };
        }

        try {
          // Send end call message
          if (this.matrixClient) {
            await this.matrixClient.sendMessage(callInfo.roomId, {
              msgtype: MsgType.Text,
              body: `📞 Call ended (Call ID: ${callId})`
            });
          }
          
          // Emit call event
          this.callEventSubject.next({
            type: CallEventType.CALL_EVENT_ENDED,
            timestamp: new Date(),
            callId,
            state: CallState.CALL_STATE_ENDED,
            metadata: { roomId: callInfo.roomId, reason: request.reason || 'user_hangup' }
          });
          
          // Remove from active calls
          this.activeWebRTCCalls.delete(callId);
          
          return {
            success: true,
            message: 'Call ended successfully'
          };
          
        } catch (error) {
          console.error('Failed to end Matrix call:', error);
          return {
            success: false,
            message: `Failed to end call: ${error}`
          };
        }
      },

      // Media negotiation
      negotiateMedia: async (request: MediaNegotiationRequest, context: CallContext): Promise<MediaNegotiation> => {
        console.log('Received media negotiation request:', request);
        
        // Simple negotiation logic - select compatible formats
        const selectedVideoCodec = request.localCapabilities?.videoCodecs.find(codec => 
          ['VP8', 'VP9', 'H264'].includes(codec)) || 'VP8';
        const selectedAudioCodec = request.localCapabilities?.audioCodecs.find(codec => 
          ['OPUS', 'G722'].includes(codec)) || 'OPUS';
        
        return {
          selectedVideoCodec,
          selectedAudioCodec,
          selectedResolution: { width: 1280, height: 720, framerate: 30 },
          directStreaming: true,
          transcodingRequired: false,
          streamUrl: `matrix://webrtc/${request.callId}/negotiated`
        };
      },

      // Stream call events
      streamCallEvents: (request: Empty, context: CallContext): ServerStreamingMethodResult<CallEvent> => {
        console.log('Client subscribed to call events');
        // Convert Subject to async iterable
        const subject = this.callEventSubject;
        return {
          [Symbol.asyncIterator]: async function* () {
            const subscription = subject.subscribe();
            try {
              while (true) {
                const promise = new Promise<CallEvent>((resolve, reject) => {
                  const sub = subject.subscribe({
                    next: resolve,
                    error: reject,
                    complete: () => reject(new Error('Stream completed'))
                  });
                  // Clean up on next tick
                  setTimeout(() => sub.unsubscribe(), 0);
                });
                yield await promise;
              }
            } finally {
              subscription.unsubscribe();
            }
          }
        };
      },

      // Health check
      getHealth: async (request: Empty, context: CallContext): Promise<HealthStatus> => {
        const isHealthy = this.matrixClient !== null && this.config !== null;
        return {
          healthy: isHealthy,
          component: 'Matrix Call Plugin',
          message: isHealthy ? 'Plugin is healthy and ready' : 'Plugin not initialized',
          timestamp: new Date()
        };
      }
    };

    // Register the CallPlugin service using nice-grpc compatible format
    // Create service definition
    // Service definition no longer needed - using generated CallPluginDefinition
    
    // Register the CallPlugin service using the generated definition
    server.add(CallPluginDefinition, callPluginService);
    console.log('CallPlugin service registered successfully');
    
    await server.listen('0.0.0.0:50052');
    this.server = server;
    
    console.log('Matrix plugin gRPC server listening on port 50052');
  }

  private async initializeMatrixClient(): Promise<void> {
    if (!this.config) {
      throw new Error('Matrix configuration not provided');
    }

    console.log(`Initializing Matrix client for ${this.config.userId}`);
    
    this.matrixClient = createClient({
      baseUrl: this.config.homeserver,
      accessToken: this.config.accessToken,
      userId: this.config.userId
    });

    // Set up event handlers
    this.matrixClient.on(ClientEvent.Sync, (state) => {
      console.log(`Matrix sync state: ${state}`);
    });

    this.matrixClient.on(RoomEvent.Timeline, (event, _room) => {
      // Handle incoming messages and call events
      if (event.getType() === 'm.call.invite') {
        console.log('Received incoming call invite:', event);
        // TODO: Handle incoming WebRTC calls
      }
    });

    // Start the Matrix client
    await this.matrixClient.startClient();
    
    console.log('Matrix client started successfully');
  }

  async shutdown(): Promise<void> {
    console.log('Shutting down Matrix plugin...');
    
    if (this.matrixClient) {
      this.matrixClient.stopClient();
    }
    
    if (this.server) {
      this.server.shutdown();
    }
    
    // Complete the call events stream
    this.callEventSubject.complete();
    
    console.log('Matrix plugin shut down successfully');
  }
}

// Main entry point
async function main(): Promise<void> {
  const plugin = new MatrixCallPlugin();
  
  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    console.log('Received SIGINT, shutting down...');
    await plugin.shutdown();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    console.log('Received SIGTERM, shutting down...');
    await plugin.shutdown();
    process.exit(0);
  });

  try {
    await plugin.initialize();
  } catch (error) {
    console.error('Failed to start Matrix plugin:', error);
    process.exit(1);
  }
}

// Start the plugin if this file is run directly
if (require.main === module) {
  main().catch((error) => {
    console.error('Fatal error in Matrix plugin:', error);
    process.exit(1);
  });
}

export { MatrixCallPlugin };