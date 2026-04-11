/* ────────────────────────────────────────────────
 *  Media Store  –  camera/screen permissions, VAD state, snapshot
 * ──────────────────────────────────────────────── */
import { create } from "zustand";

interface MediaState {
  // Permission states
  cameraGranted: boolean;
  screenGranted: boolean;
  screenShareSupported: boolean;
  micGranted: boolean;
  micSupported: boolean;

  // Media streams (kept alive for snapshot capture)
  cameraStream: MediaStream | null;
  screenStream: MediaStream | null;

  // VAD state
  isListening: boolean; // VAD detected speech in progress
  vadActive: boolean; // VAD module running
  micMuted: boolean; // user manually muted mic
  micAudioLevel: number; // 0-1 RMS for visualization

  // Snapshot
  snapshotInterval: number; // seconds
  snapshotActive: boolean;

  // VAD sensitivity (positive speech threshold, lower = more sensitive)
  vadSensitivity: number;

  // Actions
  setCameraGranted: (granted: boolean) => void;
  setScreenGranted: (granted: boolean) => void;
  setScreenShareSupported: (supported: boolean) => void;
  setMicGranted: (granted: boolean) => void;
  setIsListening: (listening: boolean) => void;
  setVadActive: (active: boolean) => void;
  setMicMuted: (muted: boolean) => void;
  toggleMicMute: () => void;
  setMicAudioLevel: (level: number) => void;
  setSnapshotInterval: (seconds: number) => void;
  setSnapshotActive: (active: boolean) => void;
  setVadSensitivity: (sensitivity: number) => void;
  requestCamera: () => Promise<boolean>;

  /** Request screen share via getDisplayMedia. Returns true if granted. */
  requestScreenShare: () => Promise<boolean>;
  /** Request microphone permission via getUserMedia. Returns true if granted. */
  requestMicrophone: () => Promise<boolean>;
  /** Stop screen share and release the stream. */
  stopScreenShare: () => void;
  /** Stop camera and release the stream. */
  stopCamera: () => void;
}

export const useMediaStore = create<MediaState>((set, get) => ({
  cameraGranted: false,
  screenGranted: false,
  screenShareSupported: typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getDisplayMedia,
  micGranted: false,
  micSupported: typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia,
  cameraStream: null,
  screenStream: null,
  isListening: false,
  vadActive: false,
  micMuted: false,
  micAudioLevel: 0,
  snapshotInterval: 60,
  snapshotActive: false,
  vadSensitivity: 0.35,

  setCameraGranted: (granted) => set({ cameraGranted: granted }),
  setScreenGranted: (granted) => set({ screenGranted: granted }),
  setScreenShareSupported: (supported) =>
    set({ screenShareSupported: supported }),
  setMicGranted: (granted) => set({ micGranted: granted }),
  setIsListening: (listening) => set({ isListening: listening }),
  setVadActive: (active) => set({ vadActive: active }),
  setMicMuted: (muted) => set({ micMuted: muted }),
  toggleMicMute: () => set((s) => ({ micMuted: !s.micMuted })),
  setMicAudioLevel: (level) => set({ micAudioLevel: level }),
  setSnapshotInterval: (seconds) => set({ snapshotInterval: seconds }),
  setSnapshotActive: (active) => set({ snapshotActive: active }),
  setVadSensitivity: (sensitivity) => set({ vadSensitivity: sensitivity }),

  requestCamera: async () => {
    const existingStream = get().cameraStream;
    if (existingStream) {
      // Check if stream is still active
      const tracks = existingStream.getVideoTracks();
      if (tracks.length > 0 && tracks[0].readyState === "live") {
        set({ cameraGranted: true });
        return true;
      }
      // Stream is dead, clean it up
      existingStream.getTracks().forEach((t) => t.stop());
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1280, min: 640 },
          height: { ideal: 720, min: 360 },
        },
        audio: false,
      });
      const videoTrack = stream.getVideoTracks()[0];
      if (videoTrack) {
        const onEnded = () => {
          videoTrack.removeEventListener("ended", onEnded);
          set({ cameraGranted: false, cameraStream: null });
        };
        videoTrack.addEventListener("ended", onEnded);
      }
      set({ cameraGranted: true, cameraStream: stream });
      return true;
    } catch (err) {
      console.warn("[MediaStore] Camera permission denied:", err);
      set({ cameraGranted: false, cameraStream: null });
      return false;
    }
  },

  requestScreenShare: async () => {
    const existingStream = get().screenStream;
    if (existingStream) {
      // Check if stream is still active
      const tracks = existingStream.getVideoTracks();
      if (tracks.length > 0 && tracks[0].readyState === "live") {
        set({ screenGranted: true });
        return true;
      }
      // Stream is dead, clean it up
      existingStream.getTracks().forEach((t) => t.stop());
    }

    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: "monitor" },
        audio: false,
      });
      const videoTrack = stream.getVideoTracks()[0];
      if (videoTrack) {
        const onEnded = () => {
          videoTrack.removeEventListener("ended", onEnded);
          set({ screenGranted: false, screenStream: null });
          console.log("[MediaStore] Screen share ended by user");
        };
        videoTrack.addEventListener("ended", onEnded);
      }
      set({ screenGranted: true, screenStream: stream });
      return true;
    } catch (err) {
      console.warn("[MediaStore] Screen share denied:", err);
      set({ screenGranted: false, screenStream: null });
      return false;
    }
  },

  requestMicrophone: async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      set({ micGranted: false });
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });
      stream.getTracks().forEach((track) => track.stop());
      set({ micGranted: true, micMuted: false });
      return true;
    } catch (err) {
      console.warn("[MediaStore] Microphone permission denied:", err);
      set({ micGranted: false });
      return false;
    }
  },

  stopScreenShare: () => {
    const stream = get().screenStream;
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    set({ screenGranted: false, screenStream: null });
  },

  stopCamera: () => {
    const stream = get().cameraStream;
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
    }
    set({ cameraGranted: false, cameraStream: null });
  },
}));
