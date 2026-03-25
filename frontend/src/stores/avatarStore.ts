import { create } from "zustand";
import type { AudioMessage, ModelInfo } from "@/lib/protocol";

interface StreamChunk {
  audio: string;
  expression: string;
}

interface AvatarState {
  pendingAudioMessages: AudioMessage[];
  modelInfo: ModelInfo["model_info"] | null;
  currentExpression: string;
  playbackInterruptVersion: number;
  /** Streaming TTS state */
  pendingStreamChunks: StreamChunk[];
  streamEndReceived: boolean;
  streamActiveVersion: number;
  /** True while a streaming session is in progress (reset only by resetStreamState) */
  isStreamingActive: boolean;
  enqueueAudioMessage: (msg: AudioMessage) => void;
  shiftAudioMessage: () => void;
  clearAudioMessages: () => void;
  setCurrentExpression: (expression: string) => void;
  requestPlaybackInterrupt: () => void;
  setModelInfo: (info: ModelInfo["model_info"]) => void;
  enqueueStreamChunk: (audio: string, expression: string) => void;
  endAudioStream: () => void;
  shiftStreamChunk: () => StreamChunk | undefined;
  resetStreamState: () => void;
}

export const useAvatarStore = create<AvatarState>((set, get) => ({
  pendingAudioMessages: [],
  modelInfo: null,
  currentExpression: "neutral",
  playbackInterruptVersion: 0,
  pendingStreamChunks: [],
  streamEndReceived: false,
  streamActiveVersion: 0,
  isStreamingActive: false,
  enqueueAudioMessage: (msg) =>
    set((state) => ({
      pendingAudioMessages: [...state.pendingAudioMessages, msg],
    })),
  shiftAudioMessage: () =>
    set((state) => ({
      pendingAudioMessages: state.pendingAudioMessages.slice(1),
    })),
  clearAudioMessages: () => set({ pendingAudioMessages: [] }),
  setCurrentExpression: (expression) =>
    set({ currentExpression: (expression || "neutral").toLowerCase() }),
  requestPlaybackInterrupt: () =>
    set((state) => ({ playbackInterruptVersion: state.playbackInterruptVersion + 1 })),
  setModelInfo: (info) => set({ modelInfo: info }),
  enqueueStreamChunk: (audio, expression) =>
    set((state) => ({
      pendingStreamChunks: [...state.pendingStreamChunks, { audio, expression }],
      // Only bump version (= create new player) when no session is currently active.
      // Once isStreamingActive is true it stays true until resetStreamState() is called.
      streamActiveVersion: !state.isStreamingActive
        ? state.streamActiveVersion + 1
        : state.streamActiveVersion,
      isStreamingActive: true,
    })),
  endAudioStream: () => set({ streamEndReceived: true }),
  shiftStreamChunk: () => {
    const chunks = get().pendingStreamChunks;
    if (chunks.length === 0) return undefined;
    const first = chunks[0];
    set({ pendingStreamChunks: chunks.slice(1) });
    return first;
  },
  resetStreamState: () =>
    set({ pendingStreamChunks: [], streamEndReceived: false, isStreamingActive: false }),
}));