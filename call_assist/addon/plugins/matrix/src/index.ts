#!/usr/bin/env node

import { createServer } from "nice-grpc";
import {
  MatrixClient,
  createClient,
  ClientEvent,
  MatrixCall,
} from "matrix-js-sdk";
import { CallFeed } from "matrix-js-sdk/lib/webrtc/callFeed";
import { SDPStreamMetadataPurpose } from "matrix-js-sdk/lib/webrtc/callEventTypes";
import { Subject } from "rxjs";
import * as wrtc from "@roamhq/wrtc";
import { spawn, ChildProcess } from "child_process";
import { Readable } from "stream";

import "./polyfills"; // Import WebRTC polyfills for Node.js environment

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
  ServerStreamingMethodResult,
} from "./proto_gen/call_plugin";
import {
  CallState,
  CallEvent,
  CallEventType,
  MediaCapabilities,
  MediaNegotiation,
  HealthStatus,
  ContactUpdate,
  ContactUpdateType,
} from "./proto_gen/common";
import { Empty } from "./proto_gen/google/protobuf/empty";
import type { CallContext } from "nice-grpc-common";
import { RTCAudioSource, RTCVideoSource } from "@roamhq/wrtc/types/nonstandard";

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
  videoSource?: RTCVideoSource; // RTCVideoSource for WebRTC
  audioSource?: RTCAudioSource; // RTCAudioSource for WebRTC
  isActive: boolean;
  cameraStreamUrl: string;
  frameBuffer: Buffer[];
  frameInterval?: NodeJS.Timeout;
}

// Simplified call info for matrix-js-sdk integration
interface CallInfo {
  call: MatrixCall;
  mediaPipeline?: MediaPipeline;
  cameraStreamUrl?: string;
}

class MatrixCallPlugin {
  private matrixClient: MatrixClient | null = null;
  private server: ReturnType<typeof createServer> | null = null;
  private config: MatrixConfig | null = null;
  private activeCalls: Map<string, CallInfo> = new Map();
  private callEventSubject: Subject<CallEvent> = new Subject();

  constructor() {
    console.log("Matrix Call Plugin initializing...");
  }

  async initialize(): Promise<void> {
    console.log("Starting Matrix Call Plugin...");

    // Start gRPC server to communicate with broker
    await this.startGrpcServer();

    console.log("Matrix Call Plugin started successfully");
  }

  private async startGrpcServer(): Promise<void> {
    const server = createServer();

    // Implement CallPlugin service
    const callPluginService: CallPluginServiceImplementation = {
      // Initialize plugin with credentials
      initialize: async (
        request: PluginConfig,
        context: CallContext
      ): Promise<PluginStatus> => {
        console.log("Received initialize request:", request);

        try {
          this.config = {
            homeserver: request.credentials.homeserver,
            accessToken: request.credentials.access_token,
            userId: request.credentials.user_id,
            accountId: request.accountId,
            displayName: request.displayName,
          };

          console.log(
            `Initializing Matrix plugin for account: ${request.displayName} (${request.accountId})`
          );

          // Initialize Matrix client
          await this.initializeMatrixClient();

          return {
            initialized: true,
            authenticated: true,
            message: "Matrix plugin initialized successfully",
            capabilities: {
              videoCodecs: ["VP8", "VP9", "H264"],
              audioCodecs: ["OPUS", "G722"],
              supportedResolutions: [
                { width: 1280, height: 720, framerate: 30 },
                { width: 1920, height: 1080, framerate: 30 },
              ],
              hardwareAcceleration: false,
              webrtcSupport: true,
              maxBandwidthKbps: 2000,
            },
          };
        } catch (error) {
          console.error("Matrix plugin initialization failed:", error);
          return {
            initialized: false,
            authenticated: false,
            message: `Initialization failed: ${error}`,
            capabilities: undefined,
          };
        }
      },

      // Shutdown plugin
      shutdown: async (
        request: Empty,
        context: CallContext
      ): Promise<Empty> => {
        console.log("Received shutdown request");
        await this.shutdown();
        return {};
      },

      // Start a call
      startCall: async (
        request: CallStartRequest,
        context: CallContext
      ): Promise<CallStartResponse> => {
        console.log("Received start call request:", request);

        if (!this.matrixClient || !this.config) {
          return {
            success: false,
            message: "Matrix client not initialized",
            state: CallState.CALL_STATE_FAILED,
            remoteStreamUrl: "",
          };
        }

        try {
          // Parse Matrix room ID from target address
          const roomId = request.targetAddress;
          const callId = request.callId;

          // Validate room before starting call
          const validation = await this.validateCallTarget(roomId);
          if (!validation.valid) {
            return {
              success: false,
              message: `Cannot start call: ${validation.reason}`,
              state: CallState.CALL_STATE_FAILED,
              remoteStreamUrl: "",
            };
          }

          // Create a mock implementation of enumerateDevices that creates
          // and returns the devices we were given in this request, so that
          // matrix-js-sdk finds them

          global.navigator.mediaDevices.enumerateDevices = async () => {
            const devices: MediaDeviceInfo[] = [];

            // Add mock video input device for camera stream
            if (request.cameraStreamUrl) {
              devices.push({
                deviceId: "camera-0",
                groupId: "camera-group-0",
                kind: "videoinput",
                label: "Call Assist Camera Stream",
                toJSON: () => {},
              });
            }

            // Add mock audio input device
            devices.push({
              deviceId: "audio-input-0",
              groupId: "audio-group-0",
              kind: "audioinput",
              label: "Call Assist Audio Input",
              toJSON: () => {},
            });

            // Add mock audio output device
            devices.push({
              deviceId: "audio-output-0",
              groupId: "audio-group-0",
              kind: "audiooutput",
              label: "Call Assist Audio Output",
              toJSON: () => {},
            });

            return devices;
          };

          // Create call using matrix-js-sdk
          const call = this.matrixClient.createCall(roomId);

          if (!call) {
            return {
              success: false,
              message:
                "Failed to create Matrix call (unrecoverable error occurred with the matrix-js-sdk)",
              state: CallState.CALL_STATE_FAILED,
              remoteStreamUrl: "",
            };
          }

          // Set up call event handlers
          this.setupCallEventHandlers(call, callId);

          // Set up media pipeline for camera stream
          const mediaPipeline = await this.setupMediaPipeline(
            request.cameraStreamUrl
          );

          // Add media stream to the call if available

          // Store call information
          this.activeCalls.set(callId, {
            call,
            mediaPipeline,
            cameraStreamUrl: request.cameraStreamUrl,
          });
          const feed = this.createCallFeed(mediaPipeline, call);
          await call.placeCallWithCallFeeds([feed], true);
          console.log(
            `Started Matrix video call in room ${roomId} with call ID ${callId}`
          );

          // Emit call event
          this.callEventSubject.next({
            type: CallEventType.CALL_EVENT_INITIATED,
            timestamp: new Date(),
            callId,
            state: CallState.CALL_STATE_INITIATING,
            metadata: { roomId },
          });

          return {
            success: true,
            message: "Matrix video call started successfully",
            state: CallState.CALL_STATE_INITIATING,
            remoteStreamUrl: `matrix://webrtc/${callId}`,
          };
        } catch (error) {
          console.error("Failed to start Matrix video call:", error);
          return {
            success: false,
            message: `Call failed: ${error}`,
            state: CallState.CALL_STATE_FAILED,
            remoteStreamUrl: "",
          };
        }
      },

      // Accept a call
      acceptCall: async (
        request: CallAcceptRequest,
        context: CallContext
      ): Promise<CallAcceptResponse> => {
        console.log("Received accept call request:", request);

        const callId = request.callId;
        const callInfo = this.activeCalls.get(callId);

        if (!callInfo) {
          return {
            success: false,
            message: "Call not found",
            remoteStreamUrl: "",
          };
        }

        if (!this.matrixClient) {
          return {
            success: false,
            message: "Matrix client not initialized",
            remoteStreamUrl: "",
          };
        }

        try {
          // Answer the call using matrix-js-sdk
          await callInfo.call.answer();
          console.log(`Answered Matrix call ${callId}`);

          // Emit call event
          this.callEventSubject.next({
            type: CallEventType.CALL_EVENT_ANSWERED,
            timestamp: new Date(),
            callId,
            state: CallState.CALL_STATE_ACTIVE,
            metadata: { roomId: callInfo.call.roomId },
          });

          return {
            success: true,
            message: "Matrix call accepted successfully",
            remoteStreamUrl: `matrix://webrtc/${callId}/accepted`,
          };
        } catch (error) {
          console.error("Failed to accept Matrix call:", error);
          return {
            success: false,
            message: `Failed to accept call: ${error}`,
            remoteStreamUrl: "",
          };
        }
      },

      // End a call
      endCall: async (
        request: CallEndRequest,
        context: CallContext
      ): Promise<CallEndResponse> => {
        console.log("Received end call request:", request);

        const callId = request.callId;
        const callInfo = this.activeCalls.get(callId);

        if (!callInfo) {
          return {
            success: false,
            message: "Call not found",
          };
        }

        try {
          // Hangup the call using matrix-js-sdk
          callInfo.call.hangup((request.reason as any) || "user_hangup", false);
          console.log(`Hung up Matrix call ${callId}`);

          // Clean up media pipeline
          if (callInfo.mediaPipeline) {
            await this.cleanupMediaPipeline(callInfo.mediaPipeline);
          }

          // Emit call event
          this.callEventSubject.next({
            type: CallEventType.CALL_EVENT_ENDED,
            timestamp: new Date(),
            callId,
            state: CallState.CALL_STATE_ENDED,
            metadata: {
              roomId: callInfo.call.roomId,
              reason: request.reason || "user_hangup",
            },
          });

          // Remove from active calls
          this.activeCalls.delete(callId);

          return {
            success: true,
            message: "Matrix call ended successfully",
          };
        } catch (error) {
          console.error("Failed to end Matrix call:", error);
          return {
            success: false,
            message: `Failed to end call: ${error}`,
          };
        }
      },

      // Media negotiation
      negotiateMedia: async (
        request: MediaNegotiationRequest,
        context: CallContext
      ): Promise<MediaNegotiation> => {
        console.log("Received media negotiation request:", request);

        // Simple negotiation logic - select compatible formats
        const selectedVideoCodec =
          request.localCapabilities?.videoCodecs.find((codec) =>
            ["VP8", "VP9", "H264"].includes(codec)
          ) || "VP8";
        const selectedAudioCodec =
          request.localCapabilities?.audioCodecs.find((codec) =>
            ["OPUS", "G722"].includes(codec)
          ) || "OPUS";

        return {
          selectedVideoCodec,
          selectedAudioCodec,
          selectedResolution: { width: 1280, height: 720, framerate: 30 },
          directStreaming: true,
          transcodingRequired: false,
          streamUrl: `matrix://webrtc/${request.callId}/negotiated`,
        };
      },

      // Stream call events
      streamCallEvents: (
        request: Empty,
        context: CallContext
      ): ServerStreamingMethodResult<CallEvent> => {
        console.log("Client subscribed to call events");
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
                    complete: () => reject(new Error("Stream completed")),
                  });
                  // Clean up on next tick
                  setTimeout(() => sub.unsubscribe(), 0);
                });
                yield await promise;
              }
            } finally {
              subscription.unsubscribe();
            }
          },
        };
      },

      // Stream contact updates (Matrix-specific: room membership changes)
      streamContactUpdates: (
        request: Empty,
        context: CallContext
      ): ServerStreamingMethodResult<ContactUpdate> => {
        console.log("Client subscribed to contact updates");
        // For Matrix, we could stream room membership changes
        // For now, return an empty async iterator
        return {
          [Symbol.asyncIterator]: async function* () {
            // No contact updates to stream for now
            // In a real implementation, this would monitor room membership changes
          },
        };
      },

      // Health check
      getHealth: async (
        request: Empty,
        context: CallContext
      ): Promise<HealthStatus> => {
        const isHealthy = this.matrixClient !== null && this.config !== null;
        return {
          healthy: isHealthy,
          component: "Matrix Call Plugin",
          message: isHealthy
            ? "Plugin is healthy and ready"
            : "Plugin not initialized",
          timestamp: new Date(),
        };
      },
    };

    // Register the CallPlugin service using nice-grpc compatible format
    // Create service definition
    // Service definition no longer needed - using generated CallPluginDefinition

    // Register the CallPlugin service using the generated definition
    server.add(CallPluginDefinition, callPluginService);
    console.log("CallPlugin service registered successfully");

    const port = process.env.PORT || "50052";
    await server.listen(`0.0.0.0:${port}`);
    this.server = server;

    console.log(`Matrix plugin gRPC server listening on port ${port}`);
  }

  private createCallFeed(mediaPipeline: MediaPipeline, call: MatrixCall) {
    if (!this.matrixClient) {
      throw new Error(
        "Somehow tried to create a call feed without an initialized Matrix client. Bailing out."
      );
    }

    const stream = new MediaStream();

    if (mediaPipeline.videoSource) {
      const videoTrack = mediaPipeline.videoSource.createTrack();
      stream.addTrack(videoTrack);
    }

    if (mediaPipeline.audioSource) {
      const audioTrack = mediaPipeline.audioSource.createTrack();
      stream.addTrack(audioTrack);
    }

    // Place the video call
    const feed = new CallFeed({
      client: this.matrixClient,
      roomId: call.roomId,
      userId: this.matrixClient.getUserId()!,
      deviceId: this.matrixClient.getDeviceId() || undefined,
      stream: stream,
      purpose: SDPStreamMetadataPurpose.Usermedia,
      audioMuted: false,
      videoMuted: false,
      call: call,
    });
    return feed;
  }

  private async initializeMatrixClient(): Promise<void> {
    if (!this.config) {
      throw new Error("Matrix configuration not provided");
    }

    // Validate required credentials
    if (
      !this.config.homeserver ||
      !this.config.accessToken ||
      !this.config.userId
    ) {
      throw new Error(
        "Missing required Matrix credentials: homeserver, accessToken, and userId are required"
      );
    }

    console.log(`Initializing Matrix client for ${this.config.userId}`);

    this.matrixClient = createClient({
      baseUrl: this.config.homeserver,
      accessToken: this.config.accessToken,
      userId: this.config.userId,
      // Use a fixed device ID for simplicity
      // TODO: Generate this dynamically based on something from home assistant
      deviceId: "Call Assist Device",
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

    // Handle incoming calls using matrix-js-sdk Call events
    this.matrixClient.on("Call.incoming" as any, (call: MatrixCall) => {
      console.log("Received incoming Matrix call:", call.callId);
      this.handleIncomingCall(call);
    });

    // Start the Matrix client
    await this.matrixClient.startClient();

    console.log("Matrix client started successfully");
  }

  private async validateCredentials(): Promise<void> {
    if (!this.matrixClient || !this.config) {
      throw new Error("Matrix client not initialized");
    }

    try {
      // Test the credentials by calling the whoami endpoint
      const response = await this.matrixClient.whoami();

      // Verify the user ID matches what we expect
      if (response.user_id !== this.config.userId) {
        throw new Error(
          `User ID mismatch: expected ${this.config.userId}, got ${response.user_id}`
        );
      }

      console.log(`Matrix credentials validated for user: ${response.user_id}`);
    } catch (error) {
      throw new Error(`Failed to validate Matrix credentials: ${error}`);
    }
  }

  private async validateCallTarget(
    roomId: string
  ): Promise<{ valid: boolean; reason?: string }> {
    if (!this.matrixClient) {
      return { valid: false, reason: "Matrix client not initialized" };
    }

    try {
      // Check if room exists and we're a member
      const room = this.matrixClient.getRoom(roomId);
      if (!room) {
        return { valid: false, reason: "Room does not exist" };
      }

      // Check if we're a member of the room
      const myMembership = room.getMyMembership();
      if (myMembership !== "join") {
        return { valid: false, reason: "Not a member of the target room" };
      }

      // Check if room has exactly 2 members for direct calls (legacy VoIP requirement)
      const joinedMembers = room.getJoinedMembers();
      if (joinedMembers.length !== 2) {
        return {
          valid: false,
          reason: "Legacy VoIP only supports rooms with exactly 2 participants",
        };
      }

      return { valid: true };
    } catch (error) {
      return { valid: false, reason: `Room validation failed: ${error}` };
    }
  }

  private async handleIncomingCall(call: MatrixCall): Promise<void> {
    const callId = call.callId;
    console.log(
      `Handling incoming Matrix call ${callId} from room ${call.roomId}`
    );

    // Set up call event handlers
    this.setupCallEventHandlers(call, callId);

    // Store the incoming call
    this.activeCalls.set(callId, {
      call,
    });

    // Emit call event for incoming call
    this.callEventSubject.next({
      type: CallEventType.CALL_EVENT_RINGING,
      timestamp: new Date(),
      callId,
      state: CallState.CALL_STATE_RINGING,
      metadata: {
        roomId: call.roomId,
        caller: (call as any).getOpponentUserId() || "unknown",
      },
    });
  }

  private setupCallEventHandlers(call: MatrixCall, callId: string): void {
    console.log(`Setting up event handlers for call ${callId}`);

    // Handle call state changes
    call.on("state" as any, (state: string) => {
      console.log(`Call ${callId} state changed to: ${state}`);

      let callState: CallState;
      let eventType: CallEventType;

      switch (state) {
        case "ringing":
          callState = CallState.CALL_STATE_RINGING;
          eventType = CallEventType.CALL_EVENT_RINGING;
          break;
        case "connected":
          callState = CallState.CALL_STATE_ACTIVE;
          eventType = CallEventType.CALL_EVENT_ANSWERED;
          break;
        case "ended":
          callState = CallState.CALL_STATE_ENDED;
          eventType = CallEventType.CALL_EVENT_ENDED;
          break;
        default:
          callState = CallState.CALL_STATE_INITIATING;
          eventType = CallEventType.CALL_EVENT_INITIATED;
      }

      this.callEventSubject.next({
        type: eventType,
        timestamp: new Date(),
        callId,
        state: callState,
        metadata: { roomId: call.roomId, callState: state },
      });
    });

    // Handle call hangup
    call.on("hangup" as any, (reason: string) => {
      console.log(`Call ${callId} was hung up: ${reason}`);

      this.callEventSubject.next({
        type: CallEventType.CALL_EVENT_ENDED,
        timestamp: new Date(),
        callId,
        state: CallState.CALL_STATE_ENDED,
        metadata: { roomId: call.roomId, reason },
      });

      // Clean up call info
      const callInfo = this.activeCalls.get(callId);
      if (callInfo?.mediaPipeline) {
        this.cleanupMediaPipeline(callInfo.mediaPipeline);
      }
      this.activeCalls.delete(callId);
    });

    // Handle call errors
    call.on("error" as any, (error: any) => {
      console.error(`Call ${callId} error:`, error);

      this.callEventSubject.next({
        type: CallEventType.CALL_EVENT_ENDED,
        timestamp: new Date(),
        callId,
        state: CallState.CALL_STATE_FAILED,
        metadata: { roomId: call.roomId, error: error.message },
      });

      // Clean up call info
      const callInfo = this.activeCalls.get(callId);
      if (callInfo?.mediaPipeline) {
        this.cleanupMediaPipeline(callInfo.mediaPipeline);
      }
      this.activeCalls.delete(callId);
    });
  }

  private async setupMediaPipeline(
    cameraStreamUrl: string
  ): Promise<MediaPipeline> {
    console.log(`Setting up media pipeline for: ${cameraStreamUrl}`);

    const mediaPipeline: MediaPipeline = {
      isActive: false,
      cameraStreamUrl,
      frameBuffer: [],
    };

    // Create video and audio sources
    await this.createVideoSource(mediaPipeline);
    await this.createAudioSource(mediaPipeline);

    // Set up FFmpeg transcoding for RTSP to WebRTC
    await this.startFFmpegTranscoding(mediaPipeline);

    return mediaPipeline;
  }

  private async createVideoSource(mediaPipeline: MediaPipeline): Promise<any> {
    console.log("Creating video source for RTSP stream...");

    try {
      // Check if we have access to real WebRTC objects
      if (typeof wrtc !== "undefined" && wrtc.nonstandard) {
        console.log("✅ Creating video source using @roamhq/wrtc");

        // Create video source that will be fed by FFmpeg
        const videoSource = new wrtc.nonstandard.RTCVideoSource();

        // Store video source in media pipeline for FFmpeg to use
        mediaPipeline.videoSource = videoSource;

        console.log("✅ Video source created - ready for FFmpeg frames");
        return videoSource;
      } else {
        console.log(
          "ℹ️  WebRTC nonStandard API not available - using fallback"
        );
        // Fallback to synthetic video for testing
        return await this.createFallbackVideoSource(mediaPipeline);
      }
    } catch (error) {
      console.error("Error creating video source:", error);
      return null;
    }
  }

  private async createFallbackVideoSource(
    mediaPipeline: MediaPipeline
  ): Promise<any> {
    console.log("Creating fallback synthetic video source...");

    try {
      if (typeof wrtc !== "undefined" && wrtc.nonstandard) {
        const videoSource = new wrtc.nonstandard.RTCVideoSource();

        // Store for cleanup
        mediaPipeline.videoSource = videoSource;

        // Send test pattern instead of black frames
        this.startTestPatternVideoSource(videoSource);

        return videoSource;
      }
      return null;
    } catch (error) {
      console.error("Error creating fallback video source:", error);
      return null;
    }
  }

  private async createAudioSource(mediaPipeline: MediaPipeline): Promise<any> {
    console.log("Creating audio source for RTSP stream...");

    try {
      // Check if we have access to real WebRTC objects
      if (typeof wrtc !== "undefined" && wrtc.nonstandard) {
        console.log("✅ Creating audio source using @roamhq/wrtc");

        // Create audio source that will be fed by FFmpeg
        const audioSource = new wrtc.nonstandard.RTCAudioSource();

        // Store audio source in media pipeline for FFmpeg to use
        mediaPipeline.audioSource = audioSource;

        console.log("✅ Audio source created - ready for FFmpeg audio");
        return audioSource;
      } else {
        console.log(
          "ℹ️  WebRTC nonStandard API not available - skipping audio source"
        );
        return null;
      }
    } catch (error) {
      console.error("Error creating audio source:", error);
      return null;
    }
  }

  private startTestPatternVideoSource(videoSource: any): void {
    console.log("Starting test pattern video source...");

    const width = 640;
    const height = 480;

    let frameCounter = 0;

    // Send frames at 10 FPS
    const interval = setInterval(() => {
      try {
        // Create a simple test pattern with moving elements
        const frame = this.generateTestPatternFrame(
          width,
          height,
          frameCounter
        );
        videoSource.onFrame(frame);
        frameCounter++;
      } catch (error) {
        console.error("Error sending test pattern frame:", error);
        clearInterval(interval);
      }
    }, 100); // 10 FPS

    // Stop after 30 seconds (placeholder for real stream)
    setTimeout(() => {
      clearInterval(interval);
      console.log("Stopped test pattern video source");
    }, 30000);
  }

  private generateTestPatternFrame(
    width: number,
    height: number,
    frameCounter: number
  ): any {
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
          data[index] = 64; // Dark gray
        }
      }
    }

    // U and V planes (chrominance) - set to neutral values
    const uvOffset = width * height;
    const uvSize = (width * height) / 4;

    for (let i = 0; i < uvSize; i++) {
      data[uvOffset + i] = 128; // U plane
      data[uvOffset + uvSize + i] = 128; // V plane
    }

    return {
      width,
      height,
      data,
    };
  }

  private async startFFmpegTranscoding(
    mediaPipeline: MediaPipeline
  ): Promise<void> {
    console.log(
      `🎬 Starting real FFmpeg transcoding for: ${mediaPipeline.cameraStreamUrl}`
    );

    try {
      // Get FFmpeg binary path
      const ffmpegPath = "/usr/bin/ffmpeg";

      console.log(`📹 Using FFmpeg at: ${ffmpegPath}`);

      // Initialize frame buffer for raw video data
      mediaPipeline.frameBuffer = [];

      // FFmpeg command to transcode RTSP to raw YUV420P frames for WebRTC
      // Note: This focuses on video for now, audio would require separate processing
      const ffmpegArgs = [
        "-i",
        mediaPipeline.cameraStreamUrl, // Input RTSP stream
        "-f",
        "rawvideo", // Output raw video
        "-pix_fmt",
        "yuv420p", // YUV420P format for WebRTC
        "-s",
        "640x480", // Resolution (640x480)
        "-r",
        "10", // Frame rate (10 FPS)
        "-an", // No audio in this stream (video only)
        "-loglevel",
        "error", // Minimal logging
        "pipe:1", // Output to stdout
      ];

      console.log(`🚀 Starting FFmpeg with args: ${ffmpegArgs.join(" ")}`);

      // Spawn FFmpeg process
      mediaPipeline.ffmpegProcess = spawn(ffmpegPath, ffmpegArgs);

      const ffmpegProcess = mediaPipeline.ffmpegProcess;
      if (!ffmpegProcess) {
        throw new Error("Failed to start FFmpeg process");
      }

      // Handle FFmpeg stdout (raw video frames)
      if (ffmpegProcess.stdout) {
        this.handleFFmpegVideoFrames(mediaPipeline, ffmpegProcess.stdout);
      }

      // Handle FFmpeg stderr (error logging)
      if (ffmpegProcess.stderr) {
        ffmpegProcess.stderr.on("data", (data) => {
          console.error(`FFmpeg stderr: ${data.toString()}`);
        });
      }

      // Handle process events
      ffmpegProcess.on("close", (code) => {
        console.log(`FFmpeg process closed with code: ${code}`);
        mediaPipeline.isActive = false;
      });

      ffmpegProcess.on("error", (error) => {
        console.error(`FFmpeg process error: ${error}`);
        mediaPipeline.isActive = false;
      });

      console.log("✅ FFmpeg transcoding process started successfully");

      // TODO: Only activate the pipeline when the receiver answers the call
      mediaPipeline.isActive = true;
    } catch (error) {
      console.error("Error starting FFmpeg transcoding:", error);
      throw error;
    }
  }

  private handleFFmpegVideoFrames(
    mediaPipeline: MediaPipeline,
    stdout: Readable
  ): void {
    console.log("📺 Setting up FFmpeg video frame processing...");

    const frameSize = 640 * 480 * 1.5; // YUV420P: Y + U/2 + V/2 = width * height * 1.5
    let buffer = Buffer.alloc(0);

    stdout.on("data", (chunk: Buffer) => {
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

    stdout.on("end", () => {
      console.log("FFmpeg video stream ended");
    });

    stdout.on("error", (error) => {
      console.error("FFmpeg stdout error:", error);
    });
  }

  private sendFrameToWebRTC(
    mediaPipeline: MediaPipeline,
    frameData: Buffer
  ): void {
    try {
      if (!mediaPipeline.videoSource) {
        console.warn("No video source available to send frame");
        return;
      }
      if (!mediaPipeline.isActive) {
        console.warn("Media pipeline is not active, skipping frame");
        return;
      }
      // Convert raw YUV420P data to WebRTC frame format
      const frame = {
        width: 640,
        height: 480,
        data: new Uint8Array(frameData),
      };

      // Send frame to WebRTC video source
      mediaPipeline.videoSource.onFrame(frame);

      // Optional: Log frame processing (but limit to avoid spam)
      if (Math.random() < 0.01) {
        // Log ~1% of frames
        console.log(`📸 Processed RTSP frame: ${frameData.length} bytes`);
      }
    } catch (error) {
      console.error("Error sending frame to WebRTC:", error);
    }
  }

  private async cleanupMediaPipeline(
    mediaPipeline: MediaPipeline
  ): Promise<void> {
    console.log("Cleaning up media pipeline...");

    try {
      // Stop frame interval if running
      if (mediaPipeline.frameInterval) {
        clearInterval(mediaPipeline.frameInterval);
        mediaPipeline.frameInterval = undefined;
      }

      // Stop FFmpeg process if running
      if (mediaPipeline.ffmpegProcess) {
        console.log("Terminating FFmpeg process...");
        mediaPipeline.ffmpegProcess.kill("SIGTERM");

        // Wait a moment for graceful shutdown
        await new Promise((resolve) => setTimeout(resolve, 1000));

        // Force kill if still running
        if (!mediaPipeline.ffmpegProcess.killed) {
          mediaPipeline.ffmpegProcess.kill("SIGKILL");
        }
      }

      // Mark pipeline as inactive
      mediaPipeline.isActive = false;

      console.log("✅ Media pipeline cleaned up successfully");
    } catch (error) {
      console.error("Error cleaning up media pipeline:", error);
    }
  }

  async shutdown(): Promise<void> {
    console.log("Shutting down Matrix plugin...");

    // Close all active calls and clean up media pipelines
    for (const [callId, callInfo] of this.activeCalls.entries()) {
      // Hangup the call using matrix-js-sdk
      try {
        callInfo.call.hangup("user_hangup" as any, false);
        console.log(`Hung up call ${callId} during shutdown`);
      } catch (error) {
        console.error(`Error hanging up call ${callId}:`, error);
      }

      // Clean up media pipeline
      if (callInfo.mediaPipeline) {
        await this.cleanupMediaPipeline(callInfo.mediaPipeline);
        console.log(
          `Cleaned up media pipeline for call ${callId} during shutdown`
        );
      }
    }
    this.activeCalls.clear();

    if (this.matrixClient) {
      this.matrixClient.stopClient();
    }

    if (this.server) {
      this.server.shutdown();
    }

    // Complete the call events stream
    this.callEventSubject.complete();

    console.log("Matrix plugin shut down successfully");
  }
}

// Main entry point
async function main(): Promise<void> {
  const plugin = new MatrixCallPlugin();

  // Handle graceful shutdown
  process.on("SIGINT", async () => {
    console.log("Received SIGINT, shutting down...");
    await plugin.shutdown();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    console.log("Received SIGTERM, shutting down...");
    await plugin.shutdown();
    process.exit(0);
  });

  try {
    await plugin.initialize();
  } catch (error) {
    console.error("Failed to start Matrix plugin:", error);
    process.exit(1);
  }
}

// Start the plugin if this file is run directly
if (require.main === module) {
  main().catch((error) => {
    console.error("Fatal error in Matrix plugin:", error);
    process.exit(1);
  });
}

export { MatrixCallPlugin };
