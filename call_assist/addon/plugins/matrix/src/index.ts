#!/usr/bin/env node

import { createServer } from 'nice-grpc';
import { MatrixClient, createClient, ClientEvent, RoomEvent } from 'matrix-js-sdk';
import { Subject } from 'rxjs';
import * as wrtc from '@roamhq/wrtc';
import { spawn, ChildProcess } from 'child_process';
import ffmpegStatic from 'ffmpeg-static';
import { Readable } from 'stream';

// WebRTC types and interfaces
interface RTCPeerConnectionInterface {
  createOffer(): Promise<RTCSessionDescriptionInit>;
  createAnswer(): Promise<RTCSessionDescriptionInit>;
  setLocalDescription(description: RTCSessionDescriptionInit): Promise<void>;
  setRemoteDescription(description: RTCSessionDescriptionInit): Promise<void>;
  addIceCandidate(candidate: RTCIceCandidateInit): Promise<void>;
  close(): void;
  onicecandidate: ((event: any) => void) | null;
  onconnectionstatechange: ((event: any) => void) | null;
  connectionState: RTCPeerConnectionState;
  localDescription: RTCSessionDescriptionInit | null;
  remoteDescription: RTCSessionDescriptionInit | null;
}

type RTCPeerConnectionState = 'new' | 'connecting' | 'connected' | 'disconnected' | 'failed' | 'closed';

// Mock WebRTC implementation for development/testing
class MockRTCPeerConnection implements RTCPeerConnectionInterface {
  public connectionState: RTCPeerConnectionState = 'new';
  public localDescription: RTCSessionDescriptionInit | null = null;
  public remoteDescription: RTCSessionDescriptionInit | null = null;
  public onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
  public onconnectionstatechange: ((event: Event) => void) | null = null;

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    console.log('MockRTCPeerConnection: Creating offer');
    const callId = Math.random().toString(36).substring(7);
    const offer = {
      type: 'offer' as RTCSdpType,
      sdp: this.generateMockSDP(callId, 'offer')
    };
    return offer;
  }

  async createAnswer(): Promise<RTCSessionDescriptionInit> {
    console.log('MockRTCPeerConnection: Creating answer');
    const callId = Math.random().toString(36).substring(7);
    const answer = {
      type: 'answer' as RTCSdpType,
      sdp: this.generateMockSDP(callId, 'answer')
    };
    return answer;
  }

  async setLocalDescription(description: RTCSessionDescriptionInit): Promise<void> {
    console.log(`MockRTCPeerConnection: Setting local description (${description.type})`);
    this.localDescription = description;
    this.connectionState = 'connecting';
    this.onconnectionstatechange?.(new Event('connectionstatechange'));

    // Simulate ICE candidate generation
    setTimeout(() => {
      const mockCandidate: RTCIceCandidateInit = {
        candidate: 'candidate:1 1 UDP 2113667326 192.168.1.100 54400 typ host',
        sdpMLineIndex: 0,
        sdpMid: '0'
      };
      // Create a mock event object that matches the expected interface
      const mockEvent = { candidate: mockCandidate } as any;
      this.onicecandidate?.(mockEvent);
      
      // Simulate end of candidates
      setTimeout(() => {
        const endEvent = { candidate: null } as any;
        this.onicecandidate?.(endEvent);
      }, 100);
    }, 50);
  }

  async setRemoteDescription(description: RTCSessionDescriptionInit): Promise<void> {
    console.log(`MockRTCPeerConnection: Setting remote description (${description.type})`);
    this.remoteDescription = description;
    this.connectionState = 'connected';
    this.onconnectionstatechange?.(new Event('connectionstatechange'));
  }

  async addIceCandidate(candidate: RTCIceCandidateInit): Promise<void> {
    console.log(`MockRTCPeerConnection: Adding ICE candidate: ${candidate.candidate}`);
    // Mock: just log the candidate
  }

  close(): void {
    console.log('MockRTCPeerConnection: Closing connection');
    this.connectionState = 'closed';
    this.onconnectionstatechange?.(new Event('connectionstatechange'));
  }

  private generateMockSDP(callId: string, type: 'offer' | 'answer'): string {
    // Generate more realistic SDP for testing
    return `v=0\r\no=- ${Date.now()} 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0 1\r\na=msid-semantic: WMS\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:${callId.slice(0, 8)}\r\na=ice-pwd:${callId.slice(-16)}\r\na=ice-options:trickle\r\na=fingerprint:sha-256 ${this.generateFingerprint()}\r\na=setup:${type === 'offer' ? 'actpass' : 'active'}\r\na=mid:0\r\na=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level\r\na=sendrecv\r\na=msid:- ${callId}_audio\r\na=rtcp-mux\r\na=rtpmap:111 opus/48000/2\r\na=rtcp-fb:111 transport-cc\r\na=fmtp:111 minptime=10;useinbandfec=1\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:${callId.slice(0, 8)}\r\na=ice-pwd:${callId.slice(-16)}\r\na=ice-options:trickle\r\na=fingerprint:sha-256 ${this.generateFingerprint()}\r\na=setup:${type === 'offer' ? 'actpass' : 'active'}\r\na=mid:1\r\na=extmap:2 urn:ietf:params:rtp-hdrext:toffset\r\na=extmap:3 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time\r\na=extmap:4 urn:3gpp:video-orientation\r\na=sendrecv\r\na=msid:- ${callId}_video\r\na=rtcp-mux\r\na=rtcp-rsize\r\na=rtpmap:96 VP8/90000\r\na=rtcp-fb:96 goog-remb\r\na=rtcp-fb:96 transport-cc\r\na=rtcp-fb:96 ccm fir\r\na=rtcp-fb:96 nack\r\na=rtcp-fb:96 nack pli\r\n`;
  }

  private generateFingerprint(): string {
    const chars = '0123456789ABCDEF';
    const fingerprint = Array.from({length: 64}, () => chars[Math.floor(Math.random() * chars.length)]);
    return fingerprint.join('').match(/.{2}/g)!.join(':');
  }
}

// Factory function for creating RTCPeerConnection instances
function createPeerConnection(useMock: boolean = false): RTCPeerConnectionInterface {
  if (useMock || process.env.USE_MOCK_WEBRTC === 'true') {
    console.log('Using mock WebRTC implementation');
    return new MockRTCPeerConnection();
  }
  
  // Use real WebRTC implementation with TURN server configuration
  console.log('Using real WebRTC implementation');  
  const configuration: RTCConfiguration = {
    iceServers: [
      { urls: 'stun:coturn:3478' },
      { 
        urls: 'turn:coturn:3478', 
        username: 'user', 
        credential: 'pass' 
      }
    ],
    iceCandidatePoolSize: 10
  };
  
  // Cast to our interface to avoid type complexities
  return new wrtc.RTCPeerConnection(configuration) as any as RTCPeerConnectionInterface;
}

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

// Media pipeline management interface
interface MediaPipeline {
  ffmpegProcess?: ChildProcess;
  videoSource?: any; // RTCVideoSource for WebRTC
  audioSource?: any; // RTCAudioSource for WebRTC
  isActive: boolean;
  cameraStreamUrl: string;
  frameBuffer: Buffer[];
  frameInterval?: NodeJS.Timeout;
}

// Strongly typed call info interface
interface CallInfo {
  roomId: string;
  startTime: number;
  state: CallState;
  remoteStreamUrl?: string;
  peerConnection?: RTCPeerConnectionInterface;
  iceCandidates: RTCIceCandidateInit[];
  mediaPipeline?: MediaPipeline;
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
          
          // Validate room before starting call
          const validation = await this.validateCallTarget(roomId);
          if (!validation.valid) {
            return {
              success: false,
              message: `Cannot start call: ${validation.reason}`,
              state: CallState.CALL_STATE_FAILED,
              remoteStreamUrl: ''
            };
          }
          
          // Create WebRTC peer connection
          const peerConnection = createPeerConnection();
          
          // Set up peer connection event handlers
          this.setupPeerConnectionHandlers(peerConnection, callId);
          
          // Add camera stream to peer connection
          const mediaPipeline = await this.addCameraStreamToPeerConnection(peerConnection, request.cameraStreamUrl);
          
          // Create WebRTC offer for video call
          const offerDescription = await peerConnection.createOffer();
          await peerConnection.setLocalDescription(offerDescription);
          
          const offer = {
            type: 'offer',
            sdp: offerDescription.sdp
          };
          
          // Send Matrix call invite event (m.call.invite)
          const callInviteContent = {
            call_id: callId,
            version: 0,  // Use version 0 for Element Web compatibility
            offer: {
              type: 'offer',
              sdp: offer.sdp
            },
            lifetime: 30000 // 30 seconds timeout
          };
          
          await this.matrixClient.sendEvent(roomId, 'm.call.invite' as any, callInviteContent);
          console.log(`Sent m.call.invite to room ${roomId} with call ID ${callId}`);
          
          // Store call information
          this.activeWebRTCCalls.set(callId, {
            roomId,
            startTime: Date.now(),
            state: CallState.CALL_STATE_INITIATING,
            remoteStreamUrl: `matrix://webrtc/${callId}`,
            peerConnection,
            iceCandidates: [],
            mediaPipeline
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
          // Get the peer connection from call info
          let peerConnection = callInfo.peerConnection;
          
          if (!peerConnection) {
            // Create new peer connection if not exists (for incoming calls)
            peerConnection = createPeerConnection();
            this.setupPeerConnectionHandlers(peerConnection, callId);
            callInfo.peerConnection = peerConnection;
          }
          
          // Generate answer SDP  
          const answerDescription = await peerConnection.createAnswer();
          await peerConnection.setLocalDescription(answerDescription);
          
          const answer = {
            type: 'answer',
            sdp: answerDescription.sdp
          };
          
          // Send Matrix call answer event (m.call.answer)
          const callAnswerContent = {
            call_id: callId,
            version: 0,  // Use version 0 for Element Web compatibility
            answer: {
              type: 'answer',
              sdp: answer.sdp
            }
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
          // Close peer connection
          if (callInfo.peerConnection) {
            callInfo.peerConnection.close();
            console.log(`Closed peer connection for call ${callId}`);
          }
          
          // Send Matrix call hangup event (m.call.hangup)
          if (this.matrixClient) {
            const callHangupContent = {
              call_id: callId,
              version: 0,  // Use version 0 for Element Web compatibility
              reason: request.reason || 'user_hangup'
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

    // Validate required credentials
    if (!this.config.homeserver || !this.config.accessToken || !this.config.userId) {
      throw new Error('Missing required Matrix credentials: homeserver, accessToken, and userId are required');
    }

    console.log(`Initializing Matrix client for ${this.config.userId}`);
    
    this.matrixClient = createClient({
      baseUrl: this.config.homeserver,
      accessToken: this.config.accessToken,
      userId: this.config.userId
    });

    // Validate credentials by making a test API call
    try {
      await this.validateCredentials();
    } catch (error) {
      throw new Error(`Matrix credential validation failed: ${error}`);
    }

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

  private async validateCredentials(): Promise<void> {
    if (!this.matrixClient || !this.config) {
      throw new Error('Matrix client not initialized');
    }

    try {
      // Test the credentials by calling the whoami endpoint
      const response = await this.matrixClient.whoami();
      
      // Verify the user ID matches what we expect
      if (response.user_id !== this.config.userId) {
        throw new Error(`User ID mismatch: expected ${this.config.userId}, got ${response.user_id}`);
      }
      
      console.log(`Matrix credentials validated for user: ${response.user_id}`);
    } catch (error) {
      throw new Error(`Failed to validate Matrix credentials: ${error}`);
    }
  }

  private async validateCallTarget(roomId: string): Promise<{valid: boolean, reason?: string}> {
    if (!this.matrixClient) {
      return {valid: false, reason: 'Matrix client not initialized'};
    }

    try {
      // Check if room exists and we're a member
      const room = this.matrixClient.getRoom(roomId);
      if (!room) {
        return {valid: false, reason: 'Room does not exist'};
      }
      
      // Check if we're a member of the room
      const myMembership = room.getMyMembership();
      if (myMembership !== 'join') {
        return {valid: false, reason: 'Not a member of the target room'};
      }
      
      // Check if room has exactly 2 members for direct calls (legacy VoIP requirement)
      const joinedMembers = room.getJoinedMembers();
      if (joinedMembers.length !== 2) {
        return {valid: false, reason: 'Legacy VoIP only supports rooms with exactly 2 participants'};
      }
      
      return {valid: true};
    } catch (error) {
      return {valid: false, reason: `Room validation failed: ${error}`};
    }
  }

  private async rejectCall(callId: string, reason: string): Promise<void> {
    const callInfo = this.activeWebRTCCalls.get(callId);
    if (!callInfo) {
      throw new Error(`Call ${callId} not found`);
    }

    if (!this.matrixClient) {
      throw new Error('Matrix client not initialized');
    }

    // Send hangup with specific reason
    const hangupContent = {
      call_id: callId,
      version: 0,
      reason: reason  // 'user_hangup', 'invite_timeout', 'unknown_error', etc.
    };
    
    await this.matrixClient.sendEvent(callInfo.roomId, 'm.call.hangup' as any, hangupContent);
    
    // Clean up local state
    if (callInfo.peerConnection) {
      callInfo.peerConnection.close();
    }
    this.activeWebRTCCalls.delete(callId);
  }


  private async handleIncomingCallInvite(event: any, room: any): Promise<void> {
    const content = event.getContent();
    const callId = content.call_id;
    const roomId = room.roomId;
    const offer = content.offer;
    
    console.log(`Handling incoming call invite for call ${callId} in room ${roomId}`);
    
    // Create peer connection for incoming call
    const peerConnection = createPeerConnection();
    this.setupPeerConnectionHandlers(peerConnection, callId);
    
    // Set remote description from the offer
    if (offer && offer.sdp) {
      try {
        await peerConnection.setRemoteDescription(offer);
        console.log(`Set remote description for incoming call ${callId}`);
      } catch (error) {
        console.error(`Failed to set remote description for call ${callId}:`, error);
      }
    }
    
    // Store the incoming call
    this.activeWebRTCCalls.set(callId, {
      roomId,
      startTime: Date.now(),
      state: CallState.CALL_STATE_RINGING,
      remoteStreamUrl: `matrix://webrtc/${callId}/incoming`,
      peerConnection,
      iceCandidates: []
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
    const answer = content.answer;
    const callInfo = this.activeWebRTCCalls.get(callId);
    
    if (!callInfo) {
      console.warn(`Received call answer for unknown call ${callId}`);
      return;
    }
    
    console.log(`Call ${callId} was answered`);
    
    // Set remote description from the answer
    if (callInfo.peerConnection && answer && answer.sdp) {
      try {
        await callInfo.peerConnection.setRemoteDescription(answer);
        console.log(`Set remote description from answer for call ${callId}`);
        
        // Add any stored ICE candidates
        for (const candidate of callInfo.iceCandidates) {
          try {
            await callInfo.peerConnection.addIceCandidate(candidate);
            console.log(`Added stored ICE candidate for call ${callId}`);
          } catch (error) {
            console.error(`Failed to add stored ICE candidate:`, error);
          }
        }
        callInfo.iceCandidates = []; // Clear stored candidates
      } catch (error) {
        console.error(`Failed to set remote description from answer for call ${callId}:`, error);
      }
    }
    
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
    
    // Close peer connection
    if (callInfo.peerConnection) {
      callInfo.peerConnection.close();
      console.log(`Closed peer connection for remotely hung up call ${callId}`);
    }
    
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

  private setupPeerConnectionHandlers(peerConnection: RTCPeerConnectionInterface, callId: string): void {
    // Handle ICE candidates with proper trickle ICE
    peerConnection.onicecandidate = (event) => {
      const candidate = event.candidate;
      if (candidate && this.matrixClient) {
        // Send ICE candidate immediately (trickle ICE)
        const callInfo = this.activeWebRTCCalls.get(callId);
        if (callInfo) {
          const candidateContent = {
            call_id: callId,
            version: 0,  // Use version 0 for Element Web compatibility
            candidates: [candidate]
          };
          
          this.matrixClient.sendEvent(callInfo.roomId, 'm.call.candidates' as any, candidateContent);
          console.log(`Sent ICE candidate for call ${callId}: ${candidate.candidate}`);
        }
      } else {
        // End of candidates - send empty candidate to signal completion
        const callInfo = this.activeWebRTCCalls.get(callId);
        if (callInfo && this.matrixClient) {
          const endCandidatesContent = {
            call_id: callId,
            version: 0,
            candidates: []
          };
          
          this.matrixClient.sendEvent(callInfo.roomId, 'm.call.candidates' as any, endCandidatesContent);
          console.log(`ICE gathering complete for call ${callId}`);
        }
      }
    };

    // Handle connection state changes
    peerConnection.onconnectionstatechange = (event) => {
      console.log(`Call ${callId} connection state: ${peerConnection.connectionState}`);
      
      const callInfo = this.activeWebRTCCalls.get(callId);
      if (callInfo) {
        // Update call state based on peer connection state
        switch (peerConnection.connectionState) {
          case 'connected':
            callInfo.state = CallState.CALL_STATE_ACTIVE;
            this.callEventSubject.next({
              type: CallEventType.CALL_EVENT_ANSWERED,
              timestamp: new Date(),
              callId,
              state: CallState.CALL_STATE_ACTIVE,
              metadata: { roomId: callInfo.roomId }
            });
            break;
          case 'failed':
          case 'disconnected':
            callInfo.state = CallState.CALL_STATE_FAILED;
            this.callEventSubject.next({
              type: CallEventType.CALL_EVENT_ENDED,
              timestamp: new Date(),
              callId,
              state: CallState.CALL_STATE_FAILED,
              metadata: { roomId: callInfo.roomId, reason: 'connection_failed' }
            });
            break;
        }
      }
    };
  }

  private async handleIceCandidates(event: any, room: any): Promise<void> {
    const content = event.getContent();
    const callId = content.call_id;
    const roomId = room.roomId;
    const candidates = content.candidates || [];
    
    console.log(`Received ${candidates.length} ICE candidates for call ${callId} in room ${roomId}`);
    
    const callInfo = this.activeWebRTCCalls.get(callId);
    if (callInfo && callInfo.peerConnection) {
      // Add ICE candidates to peer connection
      for (const candidate of candidates) {
        try {
          await callInfo.peerConnection.addIceCandidate(candidate);
          console.log(`Added ICE candidate for call ${callId}: ${candidate.candidate}`);
        } catch (error) {
          console.error(`Failed to add ICE candidate for call ${callId}:`, error);
        }
      }
    } else {
      console.warn(`No peer connection found for call ${callId}, storing candidates`);
      // Store candidates for later if peer connection doesn't exist yet
      if (callInfo) {
        callInfo.iceCandidates.push(...candidates);
      }
    }
  }

  private async addCameraStreamToPeerConnection(peerConnection: RTCPeerConnectionInterface, cameraStreamUrl: string): Promise<MediaPipeline> {
    console.log(`Adding camera stream to WebRTC: ${cameraStreamUrl}`);
    
    try {
      // Create media pipeline for RTSP to WebRTC transcoding
      const mediaPipeline: MediaPipeline = {
        isActive: false,
        cameraStreamUrl,
        frameBuffer: []
      };

      // For real implementation, we would use FFmpeg to transcode RTSP to WebRTC
      // This is a working foundation that can be expanded with actual FFmpeg integration
      
      console.log(`🎥 Setting up media pipeline for: ${cameraStreamUrl}`);
      
      // Check if we have a real WRTC peer connection (not mock)
      if ('addTrack' in peerConnection) {
        console.log('✅ Real WebRTC peer connection detected - setting up media tracks');
        
        // Create a real video track that will be fed by FFmpeg RTSP stream
        const realVideoTrack = await this.createRealVideoTrack(mediaPipeline);
        
        // Create audio track for complete media experience
        const realAudioTrack = await this.createRealAudioTrack(mediaPipeline);
        
        if (realVideoTrack) {
          // Add the video track to the peer connection
          (peerConnection as any).addTrack(realVideoTrack);
          console.log('✅ Real video track added to peer connection');
          
          mediaPipeline.isActive = true;
        }
        
        if (realAudioTrack) {
          // Add the audio track to the peer connection
          (peerConnection as any).addTrack(realAudioTrack);
          console.log('✅ Real audio track added to peer connection');
        }
      } else {
        console.log('ℹ️  Mock WebRTC peer connection - skipping real media streaming');
        mediaPipeline.isActive = true; // Mark as active for testing
      }
      
      // Start FFmpeg process for RTSP transcoding (placeholder implementation)
      await this.startFFmpegTranscoding(mediaPipeline);
      
      return mediaPipeline;
      
    } catch (error) {
      console.error('Failed to add camera stream to peer connection:', error);
      throw error;
    }
  }

  private async createRealVideoTrack(mediaPipeline: MediaPipeline): Promise<any> {
    console.log('Creating real video track for RTSP stream...');
    
    try {
      // Check if we have access to real WebRTC objects
      if (typeof wrtc !== 'undefined' && wrtc.nonstandard) {
        console.log('✅ Creating real MediaStreamTrack using @roamhq/wrtc');
        
        // Create video source that will be fed by FFmpeg
        const videoSource = new wrtc.nonstandard.RTCVideoSource();
        const track = videoSource.createTrack();
        
        // Store video source in media pipeline for FFmpeg to use
        mediaPipeline.videoSource = videoSource;
        
        console.log('✅ Real video track created - ready for FFmpeg frames');
        return track;
      } else {
        console.log('ℹ️  WebRTC nonStandard API not available - using fallback');
        // Fallback to synthetic video for testing
        return await this.createFallbackVideoTrack(mediaPipeline);
      }
    } catch (error) {
      console.error('Error creating real video track:', error);
      return null;
    }
  }

  private async createFallbackVideoTrack(mediaPipeline: MediaPipeline): Promise<any> {
    console.log('Creating fallback synthetic video track...');
    
    try {
      if (typeof wrtc !== 'undefined' && wrtc.nonstandard) {
        const videoSource = new wrtc.nonstandard.RTCVideoSource();
        const track = videoSource.createTrack();
        
        // Store for cleanup
        mediaPipeline.videoSource = videoSource;
        
        // Send test pattern instead of black frames
        this.startTestPatternVideoSource(videoSource);
        
        return track;
      }
      return null;
    } catch (error) {
      console.error('Error creating fallback video track:', error);
      return null;
    }
  }

  private async createRealAudioTrack(mediaPipeline: MediaPipeline): Promise<any> {
    console.log('Creating real audio track for RTSP stream...');
    
    try {
      // Check if we have access to real WebRTC objects
      if (typeof wrtc !== 'undefined' && wrtc.nonstandard) {
        console.log('✅ Creating real AudioStreamTrack using @roamhq/wrtc');
        
        // Create audio source that will be fed by FFmpeg
        const audioSource = new wrtc.nonstandard.RTCAudioSource();
        const track = audioSource.createTrack();
        
        // Store audio source in media pipeline for FFmpeg to use
        mediaPipeline.audioSource = audioSource;
        
        console.log('✅ Real audio track created - ready for FFmpeg audio');
        return track;
      } else {
        console.log('ℹ️  WebRTC nonStandard API not available - skipping audio track');
        return null;
      }
    } catch (error) {
      console.error('Error creating real audio track:', error);
      return null;
    }
  }

  private startTestPatternVideoSource(videoSource: any): void {
    console.log('Starting test pattern video source...');
    
    const width = 640;
    const height = 480;
    const frameSize = width * height * 1.5; // YUV420P
    
    let frameCounter = 0;
    
    // Send frames at 10 FPS
    const interval = setInterval(() => {
      try {
        // Create a simple test pattern with moving elements
        const frame = this.generateTestPatternFrame(width, height, frameCounter);
        videoSource.onFrame(frame);
        frameCounter++;
      } catch (error) {
        console.error('Error sending test pattern frame:', error);
        clearInterval(interval);
      }
    }, 100); // 10 FPS

    // Stop after 30 seconds (placeholder for real stream)
    setTimeout(() => {
      clearInterval(interval);
      console.log('Stopped test pattern video source');
    }, 30000);
  }

  private generateTestPatternFrame(width: number, height: number, frameCounter: number): any {
    // Generate a simple test pattern with moving bars
    const frameSize = width * height * 1.5;
    const data = new Uint8ClampedArray(frameSize);
    
    // Y plane (luminance)
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const index = y * width + x;
        
        // Create moving vertical bars
        const barPosition = (frameCounter * 2) % width;
        const distanceFromBar = Math.abs(x - barPosition);
        
        if (distanceFromBar < 20) {
          data[index] = 255; // White bar
        } else if ((x + y + frameCounter) % 60 < 30) {
          data[index] = 128; // Gray checkerboard
        } else {
          data[index] = 64;  // Dark gray
        }
      }
    }
    
    // U and V planes (chrominance) - set to neutral values
    const uvOffset = width * height;
    const uvSize = width * height / 4;
    
    for (let i = 0; i < uvSize; i++) {
      data[uvOffset + i] = 128; // U plane
      data[uvOffset + uvSize + i] = 128; // V plane
    }
    
    return {
      width,
      height,
      data
    };
  }

  private async startFFmpegTranscoding(mediaPipeline: MediaPipeline): Promise<void> {
    console.log(`🎬 Starting real FFmpeg transcoding for: ${mediaPipeline.cameraStreamUrl}`);
    
    try {
      // Get FFmpeg binary path
      const ffmpegPath = ffmpegStatic;
      if (!ffmpegPath) {
        throw new Error('FFmpeg binary not found');
      }
      
      console.log(`📹 Using FFmpeg at: ${ffmpegPath}`);
      
      // Initialize frame buffer for raw video data
      mediaPipeline.frameBuffer = [];
      
      // FFmpeg command to transcode RTSP to raw YUV420P frames for WebRTC
      // Note: This focuses on video for now, audio would require separate processing
      const ffmpegArgs = [
        '-i', mediaPipeline.cameraStreamUrl,     // Input RTSP stream
        '-f', 'rawvideo',                        // Output raw video
        '-pix_fmt', 'yuv420p',                   // YUV420P format for WebRTC
        '-s', '640x480',                         // Resolution (640x480)
        '-r', '10',                              // Frame rate (10 FPS)
        '-an',                                   // No audio in this stream (video only)
        '-loglevel', 'error',                    // Minimal logging
        'pipe:1'                                 // Output to stdout
      ];
      
      console.log(`🚀 Starting FFmpeg with args: ${ffmpegArgs.join(' ')}`);
      
      // Spawn FFmpeg process
      mediaPipeline.ffmpegProcess = spawn(ffmpegPath, ffmpegArgs);
      
      const ffmpegProcess = mediaPipeline.ffmpegProcess;
      if (!ffmpegProcess) {
        throw new Error('Failed to start FFmpeg process');
      }
      
      // Handle FFmpeg stdout (raw video frames)
      if (ffmpegProcess.stdout) {
        this.handleFFmpegVideoFrames(mediaPipeline, ffmpegProcess.stdout);
      }
      
      // Handle FFmpeg stderr (error logging)
      if (ffmpegProcess.stderr) {
        ffmpegProcess.stderr.on('data', (data) => {
          console.error(`FFmpeg stderr: ${data.toString()}`);
        });
      }
      
      // Handle process events
      ffmpegProcess.on('close', (code) => {
        console.log(`FFmpeg process closed with code: ${code}`);
        mediaPipeline.isActive = false;
      });
      
      ffmpegProcess.on('error', (error) => {
        console.error(`FFmpeg process error: ${error}`);
        mediaPipeline.isActive = false;
      });
      
      console.log('✅ FFmpeg transcoding process started successfully');
      
    } catch (error) {
      console.error('Error starting FFmpeg transcoding:', error);
      throw error;
    }
  }

  private handleFFmpegVideoFrames(mediaPipeline: MediaPipeline, stdout: Readable): void {
    console.log('📺 Setting up FFmpeg video frame processing...');
    
    const frameSize = 640 * 480 * 1.5; // YUV420P: Y + U/2 + V/2 = width * height * 1.5
    let buffer = Buffer.alloc(0);
    
    stdout.on('data', (chunk: Buffer) => {
      // Accumulate chunks into buffer
      buffer = Buffer.concat([buffer, chunk]);
      
      // Process complete frames
      while (buffer.length >= frameSize) {
        const frameData = buffer.subarray(0, frameSize);
        buffer = buffer.subarray(frameSize);
        
        // Send frame to WebRTC video source
        this.sendFrameToWebRTC(mediaPipeline, frameData);
      }
    });
    
    stdout.on('end', () => {
      console.log('FFmpeg video stream ended');
    });
    
    stdout.on('error', (error) => {
      console.error('FFmpeg stdout error:', error);
    });
  }

  private sendFrameToWebRTC(mediaPipeline: MediaPipeline, frameData: Buffer): void {
    try {
      if (mediaPipeline.videoSource && mediaPipeline.isActive) {
        // Convert raw YUV420P data to WebRTC frame format
        const frame = {
          width: 640,
          height: 480,
          data: new Uint8ClampedArray(frameData)
        };
        
        // Send frame to WebRTC video source
        mediaPipeline.videoSource.onFrame(frame);
        
        // Optional: Log frame processing (but limit to avoid spam)
        if (Math.random() < 0.01) { // Log ~1% of frames
          console.log(`📸 Processed RTSP frame: ${frameData.length} bytes`);
        }
      }
    } catch (error) {
      console.error('Error sending frame to WebRTC:', error);
    }
  }

  private async cleanupMediaPipeline(mediaPipeline: MediaPipeline): Promise<void> {
    console.log('Cleaning up media pipeline...');
    
    try {
      // Stop frame interval if running
      if (mediaPipeline.frameInterval) {
        clearInterval(mediaPipeline.frameInterval);
        mediaPipeline.frameInterval = undefined;
      }
      
      // Stop FFmpeg process if running
      if (mediaPipeline.ffmpegProcess) {
        console.log('Terminating FFmpeg process...');
        mediaPipeline.ffmpegProcess.kill('SIGTERM');
        
        // Wait a moment for graceful shutdown
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Force kill if still running
        if (!mediaPipeline.ffmpegProcess.killed) {
          mediaPipeline.ffmpegProcess.kill('SIGKILL');
        }
      }
      
      // Mark pipeline as inactive
      mediaPipeline.isActive = false;
      
      console.log('✅ Media pipeline cleaned up successfully');
      
    } catch (error) {
      console.error('Error cleaning up media pipeline:', error);
    }
  }

  async shutdown(): Promise<void> {
    console.log('Shutting down Matrix plugin...');
    
    // Close all active peer connections and media pipelines
    for (const [callId, callInfo] of this.activeWebRTCCalls.entries()) {
      if (callInfo.peerConnection) {
        callInfo.peerConnection.close();
        console.log(`Closed peer connection for call ${callId} during shutdown`);
      }
      
      // Clean up media pipeline
      if (callInfo.mediaPipeline) {
        await this.cleanupMediaPipeline(callInfo.mediaPipeline);
        console.log(`Cleaned up media pipeline for call ${callId} during shutdown`);
      }
    }
    this.activeWebRTCCalls.clear();
    
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