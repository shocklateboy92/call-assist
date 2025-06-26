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
  HealthStatus,
  ContactUpdate,
  ContactUpdateType
} from './proto_gen/common';
import { Empty } from './proto_gen/google/protobuf/empty';
import type { CallContext } from 'nice-grpc-common';

// Matrix plugin configuration interface
interface MatrixConfig {
  homeserver: string;
  accessToken: string;
  userId: string;
  accountId: string;
  displayName: string;
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
            userId: request.credentials.user_id,
            accountId: request.accountId,
            displayName: request.displayName
          };
          
          console.log(`Initializing Matrix plugin for account: ${request.displayName} (${request.accountId})`);
          
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
          
          // Create WebRTC offer for video call
          const offer = {
            type: 'offer',
            sdp: this.generateMockWebRTCOffer(callId)
          };
          
          // Send Matrix call invite event (m.call.invite)
          const callInviteContent = {
            call_id: callId,
            version: 1,
            type: 'offer',
            sdp: offer.sdp,
            offer,
            lifetime: 30000, // 30 seconds timeout
            party_id: this.config.userId
          };
          
          await this.matrixClient.sendEvent(roomId, 'm.call.invite' as any, callInviteContent);
          console.log(`Sent m.call.invite to room ${roomId} with call ID ${callId}`);
          
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
            message: 'WebRTC call invite sent successfully',
            state: CallState.CALL_STATE_INITIATING,
            remoteStreamUrl: `matrix://webrtc/${callId}`
          };
          
        } catch (error) {
          console.error('Failed to start Matrix WebRTC call:', error);
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

        if (!this.matrixClient) {
          return {
            success: false,
            message: 'Matrix client not initialized',
            remoteStreamUrl: ''
          };
        }

        try {
          // Generate answer SDP
          const answer = {
            type: 'answer',
            sdp: this.generateMockWebRTCAnswer(callId)
          };
          
          // Send Matrix call answer event (m.call.answer)
          const callAnswerContent = {
            call_id: callId,
            version: 1,
            type: 'answer',
            sdp: answer.sdp,
            answer,
            party_id: this.config?.userId
          };
          
          await this.matrixClient.sendEvent(callInfo.roomId, 'm.call.answer' as any, callAnswerContent);
          console.log(`Sent m.call.answer for call ${callId}`);
          
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
            message: 'WebRTC call accepted successfully',
            remoteStreamUrl: callInfo.remoteStreamUrl || ''
          };
        } catch (error) {
          console.error('Failed to accept Matrix WebRTC call:', error);
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
          // Send Matrix call hangup event (m.call.hangup)
          if (this.matrixClient) {
            const callHangupContent = {
              call_id: callId,
              version: 1,
              reason: request.reason || 'user_hangup',
              party_id: this.config?.userId
            };
            
            await this.matrixClient.sendEvent(callInfo.roomId, 'm.call.hangup' as any, callHangupContent);
            console.log(`Sent m.call.hangup for call ${callId}`);
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
            message: 'WebRTC call ended successfully'
          };
          
        } catch (error) {
          console.error('Failed to end Matrix WebRTC call:', error);
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

      // Stream contact updates (Matrix-specific: room membership changes)
      streamContactUpdates: (request: Empty, context: CallContext): ServerStreamingMethodResult<ContactUpdate> => {
        console.log('Client subscribed to contact updates');
        // For Matrix, we could stream room membership changes
        // For now, return an empty async iterator
        return {
          [Symbol.asyncIterator]: async function* () {
            // No contact updates to stream for now
            // In a real implementation, this would monitor room membership changes
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
    
    const port = process.env.PORT || '50052';
    await server.listen(`0.0.0.0:${port}`);
    this.server = server;

    console.log(`Matrix plugin gRPC server listening on port ${port}`);
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

    this.matrixClient.on(RoomEvent.Timeline, (event, room) => {
      // Handle incoming messages and call events
      const eventType = event.getType();
      const content = event.getContent();
      
      if (eventType === 'm.call.invite') {
        console.log('Received incoming call invite:', event);
        this.handleIncomingCallInvite(event, room);
      } else if (eventType === 'm.call.answer') {
        console.log('Received call answer:', event);
        this.handleCallAnswer(event, room);
      } else if (eventType === 'm.call.hangup') {
        console.log('Received call hangup:', event);
        this.handleCallHangup(event, room);
      } else if (eventType === 'm.call.candidates') {
        console.log('Received ICE candidates:', event);
        this.handleIceCandidates(event, room);
      }
    });

    // Start the Matrix client
    await this.matrixClient.startClient();
    
    console.log('Matrix client started successfully');
  }

  private generateMockWebRTCOffer(callId: string): string {
    // Generate a mock SDP offer for WebRTC
    // In a real implementation, this would come from a WebRTC peer connection
    return `v=0
o=- ${Date.now()} 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0 1
a=msid-semantic: WMS
m=audio 9 UDP/TLS/RTP/SAVPF 111
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:${callId.slice(0, 8)}
a=ice-pwd:${callId.slice(-16)}
a=ice-options:trickle
a=fingerprint:sha-256 ${this.generateFingerprint()}
a=setup:actpass
a=mid:0
a=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level
a=sendrecv
a=msid:- ${callId}_audio
a=rtcp-mux
a=rtpmap:111 opus/48000/2
a=rtcp-fb:111 transport-cc
a=fmtp:111 minptime=10;useinbandfec=1
m=video 9 UDP/TLS/RTP/SAVPF 96
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:${callId.slice(0, 8)}
a=ice-pwd:${callId.slice(-16)}
a=ice-options:trickle
a=fingerprint:sha-256 ${this.generateFingerprint()}
a=setup:actpass
a=mid:1
a=extmap:2 urn:ietf:params:rtp-hdrext:toffset
a=extmap:3 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time
a=extmap:4 urn:3gpp:video-orientation
a=sendrecv
a=msid:- ${callId}_video
a=rtcp-mux
a=rtcp-rsize
a=rtpmap:96 VP8/90000
a=rtcp-fb:96 goog-remb
a=rtcp-fb:96 transport-cc
a=rtcp-fb:96 ccm fir
a=rtcp-fb:96 nack
a=rtcp-fb:96 nack pli
`;
  }

  private generateFingerprint(): string {
    // Generate a mock SHA-256 fingerprint
    const chars = '0123456789ABCDEF';
    const fingerprint = Array.from({length: 64}, () => chars[Math.floor(Math.random() * chars.length)]);
    return fingerprint.join('').match(/.{2}/g)!.join(':');
  }

  private generateMockWebRTCAnswer(callId: string): string {
    // Generate a mock SDP answer for WebRTC
    // In a real implementation, this would come from a WebRTC peer connection
    return `v=0\r\no=- ${Date.now()} 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0 1\r\na=msid-semantic: WMS\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:${callId.slice(0, 8)}\r\na=ice-pwd:${callId.slice(-16)}\r\na=ice-options:trickle\r\na=fingerprint:sha-256 ${this.generateFingerprint()}\r\na=setup:active\r\na=mid:0\r\na=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level\r\na=sendrecv\r\na=msid:- ${callId}_audio_answer\r\na=rtcp-mux\r\na=rtpmap:111 opus/48000/2\r\na=rtcp-fb:111 transport-cc\r\na=fmtp:111 minptime=10;useinbandfec=1\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:${callId.slice(0, 8)}\r\na=ice-pwd:${callId.slice(-16)}\r\na=ice-options:trickle\r\na=fingerprint:sha-256 ${this.generateFingerprint()}\r\na=setup:active\r\na=mid:1\r\na=extmap:2 urn:ietf:params:rtp-hdrext:toffset\r\na=extmap:3 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time\r\na=extmap:4 urn:3gpp:video-orientation\r\na=sendrecv\r\na=msid:- ${callId}_video_answer\r\na=rtcp-mux\r\na=rtcp-rsize\r\na=rtpmap:96 VP8/90000\r\na=rtcp-fb:96 goog-remb\r\na=rtcp-fb:96 transport-cc\r\na=rtcp-fb:96 ccm fir\r\na=rtcp-fb:96 nack\r\na=rtcp-fb:96 nack pli\r\n`;
  }

  private async handleIncomingCallInvite(event: any, room: any): Promise<void> {
    const content = event.getContent();
    const callId = content.call_id;
    const roomId = room.roomId;
    
    console.log(`Handling incoming call invite for call ${callId} in room ${roomId}`);
    
    // Store the incoming call
    this.activeWebRTCCalls.set(callId, {
      roomId,
      startTime: Date.now(),
      state: CallState.CALL_STATE_RINGING,
      remoteStreamUrl: `matrix://webrtc/${callId}/incoming`
    });
    
    // Emit call event for incoming call
    this.callEventSubject.next({
      type: CallEventType.CALL_EVENT_RINGING,
      timestamp: new Date(),
      callId,
      state: CallState.CALL_STATE_RINGING,
      metadata: { 
        roomId,
        caller: event.getSender(),
        offer: content.offer
      }
    });
  }

  private async handleCallAnswer(event: any, room: any): Promise<void> {
    const content = event.getContent();
    const callId = content.call_id;
    const roomId = room.roomId;
    const callInfo = this.activeWebRTCCalls.get(callId);
    
    if (!callInfo) {
      console.warn(`Received call answer for unknown call ${callId}`);
      return;
    }
    
    console.log(`Call ${callId} was answered`);
    
    // Update call state
    callInfo.state = CallState.CALL_STATE_ACTIVE;
    callInfo.remoteStreamUrl = `matrix://webrtc/${callId}/active`;
    this.activeWebRTCCalls.set(callId, callInfo);
    
    // Emit call answered event
    this.callEventSubject.next({
      type: CallEventType.CALL_EVENT_ANSWERED,
      timestamp: new Date(),
      callId,
      state: CallState.CALL_STATE_ACTIVE,
      metadata: { 
        roomId: roomId,
        answer: content.answer
      }
    });
  }

  private async handleCallHangup(event: any, room: any): Promise<void> {
    const content = event.getContent();
    const callId = content.call_id;
    const roomId = room.roomId;
    const callInfo = this.activeWebRTCCalls.get(callId);
    
    if (!callInfo) {
      console.warn(`Received hangup for unknown call ${callId}`);
      return;
    }
    
    console.log(`Call ${callId} was hung up: ${content.reason || 'unknown reason'}`);
    
    // Emit call ended event
    this.callEventSubject.next({
      type: CallEventType.CALL_EVENT_ENDED,
      timestamp: new Date(),
      callId,
      state: CallState.CALL_STATE_ENDED,
      metadata: { 
        roomId: roomId,
        reason: content.reason || 'remote_hangup'
      }
    });
    
    // Remove from active calls
    this.activeWebRTCCalls.delete(callId);
  }

  private async handleIceCandidates(event: any, room: any): Promise<void> {
    const content = event.getContent();
    const callId = content.call_id;
    const roomId = room.roomId;
    
    console.log(`Received ICE candidates for call ${callId} in room ${roomId}:`, content.candidates);
    
    // In a real implementation, these would be forwarded to the WebRTC peer connection
    // For now, we just log them for debugging
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