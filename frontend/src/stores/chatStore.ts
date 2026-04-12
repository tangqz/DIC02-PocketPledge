/* ────────────────────────────────────────────────
 *  Chat Store  –  messages, streaming text, agent state
 *
 *  All phases use the same chat store. In "setup" the user
 *  negotiates plans/goals with the Agent; in "active/paused"
 *  the Agent communicates supervision events verbally.
 *
 *  Tool-call results that are purely informational (balance
 *  numbers, state transitions) go to sessionStore silently.
 *  The Agent's *verbal reaction* to those results goes here.
 * ──────────────────────────────────────────────── */
import { create } from "zustand";

export type MessageRole = "user" | "agent" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  timestamp: number;
  /** Optional metadata for special rendering (e.g. plan confirmation) */
  meta?: {
    /** "tool-calling" | "plan-preview" | "alert" */
    kind?: string;
    [key: string]: unknown;
  };
}

interface ChatState {
  messages: ChatMessage[];
  streamingText: string;
  isAgentSpeaking: boolean;

  addMessage: (role: MessageRole, text: string, meta?: ChatMessage["meta"]) => void;
  appendStreamingText: (chunk: string) => void;
  /** Finalize current streaming text as a complete agent message */
  commitStreamingText: (meta?: ChatMessage["meta"]) => void;
  clearStreaming: () => void;
  setAgentSpeaking: (speaking: boolean) => void;
  clearMessages: () => void;
}

let _msgId = 0;

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streamingText: "",
  isAgentSpeaking: false,

  addMessage: (role, text, meta) => {
    const msg: ChatMessage = {
      id: `msg-${++_msgId}`,
      role,
      text,
      timestamp: Date.now(),
      meta,
    };
    set((s) => ({ messages: [...s.messages, msg] }));
  },

  appendStreamingText: (chunk) => {
    set((s) => ({ streamingText: s.streamingText + chunk }));
  },

  commitStreamingText: (meta) => {
    const text = get().streamingText.trim();
    if (text) {
      get().addMessage("agent", text, meta);
    }
    set({ streamingText: "" });
  },

  clearStreaming: () => set({ streamingText: "" }),
  setAgentSpeaking: (speaking) =>
    set((state) => (state.isAgentSpeaking === speaking ? state : { isAgentSpeaking: speaking })),
  clearMessages: () => set({ messages: [], streamingText: "" }),
}));
