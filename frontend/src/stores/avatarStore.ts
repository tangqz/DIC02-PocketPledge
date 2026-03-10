import { create } from "zustand";
import type { AudioMessage, ModelInfo } from "@/lib/protocol";

interface AvatarState {
  pendingAudioMessages: AudioMessage[];
  modelInfo: ModelInfo["model_info"] | null;
  enqueueAudioMessage: (msg: AudioMessage) => void;
  shiftAudioMessage: () => void;
  clearAudioMessages: () => void;
  setModelInfo: (info: ModelInfo["model_info"]) => void;
}

export const useAvatarStore = create<AvatarState>((set) => ({
  pendingAudioMessages: [],
  modelInfo: null,
  enqueueAudioMessage: (msg) =>
    set((state) => ({
      pendingAudioMessages: [...state.pendingAudioMessages, msg],
    })),
  shiftAudioMessage: () =>
    set((state) => ({
      pendingAudioMessages: state.pendingAudioMessages.slice(1),
    })),
  clearAudioMessages: () => set({ pendingAudioMessages: [] }),
  setModelInfo: (info) => set({ modelInfo: info }),
}));