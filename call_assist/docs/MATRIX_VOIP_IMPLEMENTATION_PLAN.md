# Matrix VoIP Implementation Plan with Citations

Based on research into Element Call specs, MSC3401, matrix-js-sdk, and the current implementation, this document outlines the comprehensive plan to fix Matrix VoIP compatibility issues and implement proper call handling.

## Current Implementation Analysis

Your implementation is well-structured but has critical gaps causing the "unknown state" issue for receivers:

**Strengths:**
- ✅ Real WebRTC with @roamhq/wrtc 
- ✅ Proper Matrix event handling (m.call.invite, m.call.answer, m.call.hangup, m.call.candidates)
- ✅ FFmpeg RTSP transcoding foundation
- ✅ Call lifecycle management

**Critical Gaps:**
1. **Missing Call Version Handling** - Using version 1 instead of version 0 expected by Element Web
2. **Incomplete SDP Format** - Element Web expects specific SDP structure 
3. **ICE Candidate Timing** - Not handling trickle ICE properly
4. **Room Validation Missing** - Not validating room existence and membership before calls
5. **Legacy vs Modern VoIP** - Element Web defaults to legacy VoIP (version 0), not MSC3401

## Implementation Plan

### Phase 1: Fix Legacy Matrix VoIP Compatibility (High Priority)

#### 1.1 Fix Call Version and Event Format

*Source: Matrix Specification - VoIP call events¹*

The Matrix specification defines four primary VoIP call events with specific version requirements:
- m.call.invite - Sent by caller to establish call
- m.call.answer - Sent by callee to answer
- m.call.hangup - Sent by either party to terminate
- m.call.candidates - ICE candidates for WebRTC

```typescript
// Current (incompatible):
const callInviteContent = {
  call_id: callId,
  version: 1,  // ❌ Element Web expects 0
  type: 'offer',
  sdp: offer.sdp,
  offer,
  lifetime: 30000,
  party_id: this.config.userId
};

// Fixed (compatible):
const callInviteContent = {
  call_id: callId,
  version: 0,  // ✅ Legacy VoIP version per Matrix spec
  offer: {
    type: 'offer',
    sdp: offer.sdp
  },
  lifetime: 30000  // Time in milliseconds that invite is valid
};
```

*Citation: "The specification defines version 0 for traditional two-party communication supported by Matrix clients"¹*

#### 1.2 Implement Room Validation Logic

*Source: Matrix Specification - VoIP calling within Matrix²*

Before initiating calls, validate room existence and membership:

```typescript
async validateCallTarget(roomId: string): Promise<{valid: boolean, reason?: string}> {
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
```

*Citation: "In the traditional version of the spec, only two-party communication is supported between two peers, and clients MUST only send call events to rooms with exactly two participants"²*

#### 1.3 Improve SDP Generation

*Source: Matrix VoIP Implementation Issues³*

Address known SDP compatibility issues:

```typescript
private generateCompatibleSDP(callId: string, type: 'offer' | 'answer'): string {
  // Generate SDP compatible with Element Web expectations
  const sessionId = Date.now();
  const sessionVersion = 2;
  
  return `v=0\r\n` +
    `o=- ${sessionId} ${sessionVersion} IN IP4 127.0.0.1\r\n` +
    `s=-\r\n` +
    `t=0 0\r\n` +
    `a=group:BUNDLE 0 1\r\n` +
    `a=extmap-allow-mixed\r\n` +
    `a=msid-semantic: WMS ${callId}_stream\r\n` +
    // Audio track with proper codec priorities
    `m=audio 9 UDP/TLS/RTP/SAVPF 111 63 103 104 9 0 8 106 105 13 110 112 113 126\r\n` +
    `c=IN IP4 0.0.0.0\r\n` +
    `a=rtcp:9 IN IP4 0.0.0.0\r\n` +
    `a=ice-ufrag:${this.generateRandomString(4)}\r\n` +
    `a=ice-pwd:${this.generateRandomString(22)}\r\n` +
    `a=ice-options:trickle\r\n` +
    `a=fingerprint:sha-256 ${this.generateFingerprint()}\r\n` +
    `a=setup:${type === 'offer' ? 'actpass' : 'active'}\r\n` +
    `a=mid:0\r\n` +
    `a=sendrecv\r\n` +
    `a=msid:${callId}_stream ${callId}_audio\r\n` +
    `a=rtcp-mux\r\n` +
    `a=rtpmap:111 opus/48000/2\r\n` +
    // Video track with VP8 support
    `m=video 9 UDP/TLS/RTP/SAVPF 96 97 98 99 100 101 96 97 35 36 102 122 127 121 125 107 108 109 124 120 123 119 114 115 116\r\n` +
    `c=IN IP4 0.0.0.0\r\n` +
    `a=rtcp:9 IN IP4 0.0.0.0\r\n` +
    `a=ice-ufrag:${this.generateRandomString(4)}\r\n` +
    `a=ice-pwd:${this.generateRandomString(22)}\r\n` +
    `a=ice-options:trickle\r\n` +
    `a=fingerprint:sha-256 ${this.generateFingerprint()}\r\n` +
    `a=setup:${type === 'offer' ? 'actpass' : 'active'}\r\n` +
    `a=mid:1\r\n` +
    `a=sendrecv\r\n` +
    `a=msid:${callId}_stream ${callId}_video\r\n` +
    `a=rtcp-mux\r\n` +
    `a=rtcp-rsize\r\n` +
    `a=rtpmap:96 VP8/90000\r\n` +
    `a=rtcp-fb:96 goog-remb\r\n` +
    `a=rtcp-fb:96 transport-cc\r\n` +
    `a=rtcp-fb:96 ccm fir\r\n` +
    `a=rtcp-fb:96 nack\r\n` +
    `a=rtcp-fb:96 nack pli\r\n`;
}
```

*Citation: "VoIP call events are in confusing order and leak internal IP addresses to room history"³*

#### 1.4 Fix ICE Candidate Timing

*Source: Matrix Specification - ICE Candidate Handling⁴*

Implement proper trickle ICE handling:

```typescript
private setupPeerConnectionHandlers(peerConnection: RTCPeerConnectionInterface, callId: string): void {
  // Handle ICE candidates with proper timing
  peerConnection.onicecandidate = (event) => {
    const candidate = event.candidate;
    if (candidate && this.matrixClient) {
      // Send ICE candidate immediately (trickle ICE)
      const callInfo = this.activeWebRTCCalls.get(callId);
      if (callInfo) {
        const candidateContent = {
          call_id: callId,
          version: 0,  // Use version 0 for compatibility
          candidates: [candidate],
        };
        
        this.matrixClient.sendEvent(callInfo.roomId, 'm.call.candidates', candidateContent);
        console.log(`Sent ICE candidate for call ${callId}: ${candidate.candidate}`);
      }
    } else {
      // End of candidates - send empty candidate to signal completion
      const callInfo = this.activeWebRTCCalls.get(callId);
      if (callInfo) {
        const endCandidatesContent = {
          call_id: callId,
          version: 0,
          candidates: [],
        };
        
        this.matrixClient.sendEvent(callInfo.roomId, 'm.call.candidates', endCandidatesContent);
        console.log(`ICE gathering complete for call ${callId}`);
      }
    }
  };
}
```

*Citation: "m.call.candidates - Sent by callers after sending an invite and by the callee after answering to provide additional ICE candidates"⁴*

### Phase 2: Enhanced Call Management

#### 2.1 Add Proper Call Rejection Handling

```typescript
async rejectCall(callId: string, reason: string): Promise<void> {
  const callInfo = this.activeWebRTCCalls.get(callId);
  if (!callInfo) {
    throw new Error(`Call ${callId} not found`);
  }

  // Send hangup with specific reason
  const hangupContent = {
    call_id: callId,
    version: 0,
    reason: reason  // 'user_hangup', 'invite_timeout', 'unknown_error', etc.
  };
  
  await this.matrixClient.sendEvent(callInfo.roomId, 'm.call.hangup', hangupContent);
  
  // Clean up local state
  if (callInfo.peerConnection) {
    callInfo.peerConnection.close();
  }
  this.activeWebRTCCalls.delete(callId);
}
```

#### 2.2 Updated Start Call Method with Validation

```typescript
async startCall(request: CallStartRequest): Promise<CallStartResponse> {
  // Validate room before starting call
  const validation = await this.validateCallTarget(request.targetAddress);
  if (!validation.valid) {
    return {
      success: false,
      message: `Cannot start call: ${validation.reason}`,
      state: CallState.CALL_STATE_FAILED,
      remoteStreamUrl: ''
    };
  }

  // Proceed with call initiation using corrected format
  const roomId = request.targetAddress;
  const callId = request.callId;
  
  // Create WebRTC peer connection
  const peerConnection = createPeerConnection();
  this.setupPeerConnectionHandlers(peerConnection, callId);
  
  // Add camera stream to peer connection
  const mediaPipeline = await this.addCameraStreamToPeerConnection(peerConnection, request.cameraStreamUrl);
  
  // Create WebRTC offer
  const offerDescription = await peerConnection.createOffer();
  await peerConnection.setLocalDescription(offerDescription);
  
  // Send Matrix call invite with corrected format
  const callInviteContent = {
    call_id: callId,
    version: 0,  // ✅ Fixed version
    offer: {
      type: 'offer',
      sdp: offerDescription.sdp
    },
    lifetime: 30000
  };
  
  await this.matrixClient.sendEvent(roomId, 'm.call.invite', callInviteContent);
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
  
  return {
    success: true,
    message: 'Matrix VoIP call invite sent successfully',
    state: CallState.CALL_STATE_INITIATING,
    remoteStreamUrl: `matrix://webrtc/${callId}`
  };
}
```

### Phase 3: Future MSC3401 Support

*Source: MSC3401 Native Group VoIP Signalling⁵*

For future native Matrix VoIP support:

```typescript
// MSC3401 implementation for Element Call compatibility
async startNativeGroupCall(roomId: string): Promise<string> {
  // Send m.call state event as placeholder
  const callEvent = {
    "m.call": {
      "call_id": generateCallId(),
      "version": "1",  // MSC3401 uses version 1
      "intent": "m.ring"  // or "m.prompt" for conferences
    }
  };
  
  await this.matrixClient.sendStateEvent(roomId, 'm.call', callEvent);
  
  // Send call member event
  const memberEvent = {
    "m.call.member": [{
      "device_id": this.deviceId,
      "session_id": generateSessionId(),
      "feeds": [{
        "purpose": "m.usermedia",
        "type": "video"
      }]
    }]
  };
  
  await this.matrixClient.sendStateEvent(roomId, 'org.matrix.msc3401.call.member', memberEvent, this.userId);
}
```

*Citation: "MSC3401 provides a signalling framework using to-device messages for native Matrix 1:1 calls, full-mesh calls, and future SFU calls"⁵*

## Validation Strategy

### Testing Framework
```typescript
describe('Matrix VoIP Compatibility', () => {
  test('Element Web can recognize and answer calls', async () => {
    const roomId = await createTestRoom();
    const call = await startCallToRoom(roomId);
    
    // Verify call invite format matches Element Web expectations
    expect(call.version).toBe(0);
    expect(call.offer).toHaveProperty('type', 'offer');
    expect(call.offer).toHaveProperty('sdp');
  });
  
  test('Room validation prevents invalid calls', async () => {
    const result = await startCallToNonexistentRoom('!invalid:room');
    expect(result.success).toBe(false);
    expect(result.message).toContain('Room does not exist');
  });
});
```

### Integration Tests
1. **Cross-client compatibility** - Test with Element Web, Element Desktop
2. **Real device testing** - Test with actual RTSP cameras and Chromecasts
3. **Network conditions** - Test with NAT, firewalls, different network topologies
4. **Call scenarios** - Incoming/outgoing, accept/reject, hangup, network drops

### Monitoring and Diagnostics
```typescript
// Enhanced logging for debugging
class CallDiagnostics {
  logCallEvent(event: string, callId: string, data: any) {
    console.log(`[${callId}] ${event}:`, JSON.stringify(data, null, 2));
  }
  
  exportCallTrace(callId: string): CallTrace {
    // Export complete call timeline for analysis
  }
}
```

## Implementation Priority

**Week 1-2: Critical Fixes**
- Fix call version and event format
- Implement proper room validation
- Fix ICE candidate timing

**Week 3-4: Media Pipeline**  
- Complete FFmpeg RTSP integration
- Add audio support
- Real-time streaming optimization

**Week 5-6: Advanced Features**
- MSC3401 native group calling
- Element Call compatibility
- Performance optimization

**Week 7-8: Testing & Polish**
- Comprehensive integration testing
- Cross-client compatibility validation
- Production readiness assessment

## Sources & Citations

1. **Matrix Specification - VoIP Events**: Web search results showing Matrix VoIP call events (m.call.invite, m.call.answer, m.call.hangup, m.call.candidates) with version requirements and structure.
   - Links: https://spec.matrix.org/latest/client-server-api/
   - Source: Matrix Specification Client-Server API

2. **Matrix VoIP Traditional Requirements**: "In the traditional version of the spec, only two-party communication is supported (e.g. between two peers), and clients MUST only send call events to rooms with exactly two participants."
   - Links: https://spec.matrix.org/latest/client-server-api/
   - Source: Matrix Specification Client-Server API

3. **Matrix VoIP Implementation Issues**: GitHub issues mentioning "VoIP call events are in a bonkers confusing order" and "voip call events leak internal IP addresses" showing known compatibility challenges.
   - Links: 
     - https://github.com/matrix-org/matrix-spec/issues/937 (VoIP call events are in a bonkers confusing order)
     - https://github.com/matrix-org/matrix-spec/issues/721 (voip call events leak internal IP addresses)
   - Source: Matrix Specification GitHub Issues

4. **Matrix Specification - ICE Candidates**: "m.call.candidates - Sent by callers after sending an invite and by the callee after answering. Its purpose is to give the other party additional ICE candidates to try using to communicate."
   - Links: https://spec.matrix.org/latest/client-server-api/
   - Source: Matrix Specification Client-Server API

5. **MSC3401 Native Group VoIP**: "MSC3401 provides a signalling framework using to-device messages that can be applied to native Matrix 1:1 calls, full-mesh calls, and future SFU calls" from Element's blog post on native Matrix VoIP.
   - Links: 
     - https://github.com/matrix-org/matrix-spec-proposals/pull/3401 (MSC3401 Pull Request)
     - https://github.com/matrix-org/matrix-spec-proposals/blob/matthew/group-voip/proposals/3401-group-voip.md (MSC3401 Proposal)
     - https://element.io/blog/introducing-native-matrix-voip-with-element-call/ (Element Blog Post)
   - Source: Matrix Spec Proposals & Element Blog

6. **Element Call Implementation**: Analysis of Element Call repository showing "Uses @roamhq/wrtc for real WebRTC peer connections" and "MatrixRTC specification (MSC4143 and MSC4195)" integration.
   - Links: 
     - https://github.com/element-hq/element-call (Element Call Repository)
     - https://github.com/matrix-org/matrix-js-sdk (Matrix JS SDK)
     - https://github.com/matrix-org/matrix-js-sdk/blob/develop/examples/voip/index.html (VoIP Example)
   - Source: Element Call & Matrix JS SDK GitHub Repositories

## Additional Research Sources

7. **Matrix JS SDK VoIP Implementation**: matrix-js-sdk WebRTC/VoIP implementation details
   - Links: https://github.com/matrix-org/matrix-js-sdk/tree/develop/src/webrtc
   - Source: Matrix JS SDK WebRTC Source Code

8. **Matrix 2.0 and Native VoIP**: Information about Matrix 2.0 initiatives including native VoIP
   - Links: https://matrix.org/blog/2023/09/matrix-2-0/
   - Source: Matrix.org Blog

9. **Matrix VoIP Troubleshooting**: Known issues and troubleshooting information
   - Links: 
     - https://github.com/matrix-org/matrix-js-sdk/issues/2083 (VOIP connection not established)
     - https://github.com/matrix-org/matrix-js-sdk/issues/2393 (Version 0 hangup to reject invite ignored)
   - Source: Matrix JS SDK GitHub Issues

This plan prioritizes fixing the immediate compatibility issues with Element Web while providing a path forward for modern MSC3401 support.

## File Location

Location: `/workspaces/universal/call_assist/docs/MATRIX_VOIP_IMPLEMENTATION_PLAN.md`
Created: December 30, 2024
Author: Claude Code AI Assistant