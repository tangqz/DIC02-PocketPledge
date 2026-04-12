/* Session store for companion-mode runtime state */
import { create } from "zustand";

export interface EmotionEvent {
  emotion: string;
  intensity: number;
  cues: string;
  suggestion: string;
  timestamp: number;
}

interface SessionState {
  isConnected: boolean;
  degradedMode: boolean;

  currentEmotion: EmotionEvent | null;
  emotionHistory: EmotionEvent[];
  activeToolCall: { tool: string; status: string } | null;
  wellbeingSyncVersion: number;

  applyEmotionUpdate: (emotion: string, intensity: number, cues: string, suggestion: string) => void;
  setActiveToolCall: (tc: { tool: string; status: string } | null) => void;
  setIsConnected: (connected: boolean) => void;
  setDegradedMode: (degraded: boolean) => void;
  markWellbeingUpdated: () => void;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  isConnected: false,
  degradedMode: false,
  currentEmotion: null,
  emotionHistory: [],
  activeToolCall: null,
  wellbeingSyncVersion: 0,

  applyEmotionUpdate: (emotion, intensity, cues, suggestion) => {
    const event: EmotionEvent = {
      emotion,
      intensity,
      cues,
      suggestion,
      timestamp: Date.now(),
    };
    set({
      currentEmotion: event,
      emotionHistory: [...get().emotionHistory.slice(-99), event],
    });
  },

  setActiveToolCall: (tc) => set({ activeToolCall: tc }),
  setIsConnected: (connected) => set({ isConnected: connected }),
  setDegradedMode: (degraded) => set({ degradedMode: degraded }),
  markWellbeingUpdated: () =>
    set((state) => ({ wellbeingSyncVersion: state.wellbeingSyncVersion + 1 })),

  reset: () =>
    set({
      isConnected: false,
      degradedMode: false,
      currentEmotion: null,
      emotionHistory: [],
      activeToolCall: null,
      wellbeingSyncVersion: 0,
    }),
}));
