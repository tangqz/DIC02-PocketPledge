import { create } from "zustand";
import type { AudioMessage, ModelInfo } from "@/lib/protocol";

interface AvatarState {
  pendingAudioMessages: AudioMessage[];
  modelInfo: ModelInfo["model_info"] | null;
  playbackInterruptVersion: number;
  enqueueAudioMessage: (msg: AudioMessage) => void;
  shiftAudioMessage: () => void;
  clearAudioMessages: () => void;
  requestPlaybackInterrupt: () => void;
  setModelInfo: (info: ModelInfo["model_info"]) => void;
}

export const useAvatarStore = create<AvatarState>((set) => ({
  pendingAudioMessages: [],
  modelInfo: null,
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
  requestPlaybackInterrupt: () =>
    set((state) => ({ playbackInterruptVersion: state.playbackInterruptVersion + 1 })),
  setModelInfo: (info) => set({ modelInfo: info }),
}));