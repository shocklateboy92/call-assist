import {
  MediaStream,
  MediaStreamTrack,
  RTCDataChannel,
  RTCDataChannelEvent,
  RTCDtlsTransport,
  RTCIceCandidate,
  RTCIceTransport,
  RTCPeerConnection,
  RTCPeerConnectionIceEvent,
  RTCRtpReceiver,
  RTCRtpSender,
  RTCRtpTransceiver,
  RTCSctpTransport,
  RTCSessionDescription,
  mediaDevices,
} from "@roamhq/wrtc";

// Set up WebRTC polyfills for matrix-js-sdk compatibility
export const setup = () => {
  global.RTCPeerConnection = RTCPeerConnection;
  global.RTCSessionDescription = RTCSessionDescription;
  global.RTCIceCandidate = RTCIceCandidate;
  global.MediaStream = MediaStream;
  global.MediaStreamTrack = MediaStreamTrack;
  global.RTCDataChannel = RTCDataChannel;
  global.RTCDataChannelEvent = RTCDataChannelEvent;
  global.RTCDtlsTransport = RTCDtlsTransport;
  global.RTCIceTransport = RTCIceTransport;
  global.RTCRtpReceiver = RTCRtpReceiver;
  global.RTCRtpSender = RTCRtpSender;
  global.RTCRtpTransceiver = RTCRtpTransceiver;
  global.RTCSctpTransport = RTCSctpTransport;
  global.RTCPeerConnectionIceEvent = RTCPeerConnectionIceEvent;

  // @ts-ignore
  global.navigator.mediaDevices = mediaDevices;

  global.window = global as any; // Mock window for matrix-js-sdk compatibility
  // This doesn't really get used, matrix-js-sdk checks for existence determine
  // if it's in a browser or not.
  global.document = {} as any;

  // @ts-ignore
  global.AudioContext = MockAudioContext;
};

// Mock AudioContext for Matrix VoIP in Node.js environment
// This is a minimal implementation to prevent crashes, not for actual audio processing

class MockAnalyserNode {
  frequencyBinCount = 1024;
  fftSize = 2048;
  minDecibels = -100;
  maxDecibels = -30;
  smoothingTimeConstant = 0.8;

  connect() {
    return this;
  }

  disconnect() {}

  getByteFrequencyData(array: Uint8Array) {
    // Fill with zeros to simulate silence
    array.fill(0);
  }

  getByteTimeDomainData(array: Uint8Array) {
    // Fill with 128 (middle value) to simulate silence
    array.fill(128);
  }

  getFloatFrequencyData(array: Float32Array) {
    // Fill with minimum decibel value to simulate silence
    array.fill(this.minDecibels);
  }

  getFloatTimeDomainData(array: Float32Array) {
    // Fill with zeros to simulate silence
    array.fill(0);
  }
}

class MockGainNode {
  gain = {
    value: 1,
    setValueAtTime: () => {},
    linearRampToValueAtTime: () => {},
    exponentialRampToValueAtTime: () => {},
  };

  connect() {
    return this;
  }

  disconnect() {}
}

class MockAudioDestinationNode {
  channelCount = 2;
  channelCountMode = "explicit";
  channelInterpretation = "speakers";
  maxChannelCount = 2;

  connect() {
    return this;
  }

  disconnect() {}
}

class MockAudioContext {
  state = "running";
  sampleRate = 44100;
  currentTime = 0;
  destination = new MockAudioDestinationNode();

  constructor() {
    // Simulate time passing
    setInterval(() => {
      this.currentTime += 0.1;
    }, 100);
  }

  createAnalyser() {
    return new MockAnalyserNode();
  }

  createGain() {
    return new MockGainNode();
  }

  createMediaStreamSource() {
    return {
      connect: () => {},
      disconnect: () => {},
    };
  }

  close() {
    return Promise.resolve();
  }

  suspend() {
    this.state = "suspended";
    return Promise.resolve();
  }

  resume() {
    this.state = "running";
    return Promise.resolve();
  }
}

setup();
