/* WarmBuddy WebSocket protocol types */

// ── Shared sub-types ──

export interface SnapshotImage {
  source: "camera" | "screen";
  data: string; // base64 JPEG
  mime_type: string;
  metadata?: {
    width?: number;
    height?: number;
    displaySurface?: string;
    facingMode?: string;
    timestamp?: number;
  };
}

// ── Upstream (Frontend → Backend)  Tx ──

export interface MicAudioData {
  type: "mic-audio-data";
  audio: number[]; // Float32 samples chunk
}

export interface MicAudioEnd {
  type: "mic-audio-end";
  images: SnapshotImage[];
}

export interface TextInput {
  type: "text-input";
  text: string;
  images?: SnapshotImage[];
  tool_result?: boolean;
}

export interface InterruptSignal {
  type: "interrupt-signal";
  text: string; // text already played before interruption
}

export interface PeriodicScreenshot {
  type: "periodic-screenshot";
  images: SnapshotImage[];
}

export interface FrontendPlaybackComplete {
  type: "frontend-playback-complete";
}

export interface CaptureContextResult {
  type: "capture-context-result";
  requestId: string;
  prompt: string;
  images: SnapshotImage[];
  error?: string;
}

export interface SetLocale {
  type: "set-locale";
  locale: "zh" | "en";
}

export interface SetCharacter {
  type: "set-character";
  characterId: string;
}

export interface PingMessage {
  type: "ping";
}

export type TxMessage =
  | MicAudioData
  | MicAudioEnd
  | TextInput
  | InterruptSignal
  | PeriodicScreenshot
  | FrontendPlaybackComplete
  | CaptureContextResult
  | SetLocale
  | SetCharacter
  | PingMessage;

// ── Downstream (Backend → Frontend)  Rx ──
//
// Messages fall into two categories:
//  1) "Agent speech" — displayed as chat text / TTS / expressions
//  2) "UI commands"  — silently applied to stores & rendered in widgets

/** Agent audio + expression + display text — rendered in Live2D + subtitles */
export interface AudioMessage {
  type: "audio";
  audio: string; // base64 WAV
  actions: {
    expressions: string[];
  };
  display_text: {
    text: string;
    name: string;
  };
}

/** Streaming text chunk from Agent's verbal output */
export interface AgentTextChunk {
  type: "agent-text-chunk";
  text: string;
}

/** Final ASR transcript for one user voice turn */
export interface UserTranscript {
  type: "user-transcript";
  text: string;
}

/** Marks the end of one Agent turn's text stream */
export interface AgentTextEnd {
  type: "agent-text-end";
}

// ─── UI Command Messages (silent side-effects) ───

/** Emotion recognition result from periodic camera captures */
export interface EmotionUpdate {
  type: "emotion-update";
  emotion: string;
  intensity: number; // 1-5
  cues: string;
  suggestion: string;
}

/**
 * Tool call status — informs the frontend that the Agent is
 * executing a tool (shown as a subtle indicator, not disruptive).
 */
export interface ToolCallStatus {
  type: "tool-call-status";
  tool: string;
  status: "calling" | "success" | "error";
  message?: string;
}

export interface ModelInfo {
  type: "model-info";
  character_id?: string;
  character?: {
    name?: string;
    displayName?: string;
    description?: string;
    languageHints?: string[];
    personaStyle?: string;
  };
  model_info: {
    name: string;
    url: string;
    kScale: number;
    emotionMap: Record<string, number>;
    idleMotionGroup: string;
    talkMotionGroup: string;
  };
}

export interface ControlMessage {
  type: "control";
  command: string;
  payload?: Record<string, unknown>;
}

/** Streaming TTS audio chunk — played gaplessly via AudioContext scheduling */
export interface AudioStreamChunk {
  type: "audio-stream-chunk";
  audio: string; // base64 WAV
  expression: string;
}

/** Signals end of a streaming TTS audio session */
export interface AudioStreamEnd {
  type: "audio-stream-end";
  expression: string;
}

export type RxMessage =
  | AudioMessage
  | AudioStreamChunk
  | AudioStreamEnd
  | AgentTextChunk
  | UserTranscript
  | AgentTextEnd
  | EmotionUpdate
  | ToolCallStatus
  | ModelInfo
  | ControlMessage;
