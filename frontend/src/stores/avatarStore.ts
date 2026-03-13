import { create } from "zustand";
import type { AudioMessage, ModelInfo } from "@/lib/protocol";

interface AvatarState {
  pendingAudioMessages: AudioMessage[];
  modelInfo: ModelInfo["model_info"] | null;
  currentExpression: string;
  playbackInterruptVersion: number;
  enqueueAudioMessage: (msg: AudioMessage) => void;
  shiftAudioMessage: () => void;
  clearAudioMessages: () => void;
  setCurrentExpression: (expression: string) => void;
  requestPlaybackInterrupt: () => void;
  setModelInfo: (info: ModelInfo["model_info"]) => void;
}

export const useAvatarStore = create<AvatarState>((set) => ({
  pendingAudioMessages: [],
  modelInfo: null,
  currentExpression: "neutral",
  playbackInterruptVersion: 0,
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
}));