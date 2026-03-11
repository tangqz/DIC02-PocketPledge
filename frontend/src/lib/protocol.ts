/* ────────────────────────────────────────────────
 *  WebSocket Message Protocol Types
 *  Authoritative contract between Frontend (A) ↔ Gateway (B)
 *
 *  Design Principle: The chatbot (Agent) drives almost ALL user
 *  operations via tool calls.  The backend translates tool-call
 *  side-effects into structured RxMessages for the frontend.
 *
 *  Feedback routing:
 *  ┌──────────────────────────┬───────────────────────────┐
 *  │  Agent verbal (emotional)│  Frontend UI (silent)     │
 *  ├──────────────────────────┼───────────────────────────┤
 *  │  Encouragement / scolding│  Balance number change    │
 *  │  Plan discussion results │  Plan panel data update   │
 *  │  Pause negotiation reply │  Timer / state badge      │
 *  │  Session greeting/bye    │  Supervision state switch │
 *  │  Achievement celebration │  Distraction indicators   │
 *  │  Emotional support       │  Session statistics       │
 *  └──────────────────────────┴───────────────────────────┘
 * ──────────────────────────────────────────────── */

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
  };
}

/**
 * Supervision state machine:
 *   setup ──(Agent: supervision.start)──→ active
 *   active ──(Agent: supervision.pause)──→ paused
 *   paused ──(Agent: supervision.resume / timeout)──→ active
 *   active|paused ──(Agent / timer-zero)──→ completed
 *
 * All transitions are triggered by the backend (Agent tool calls
 * or server-side timer events). The frontend never directly
 * mutates this state.
 */
export type SupervisionState = "setup" | "active" | "paused" | "completed";

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

export interface ResumeNow {
  type: "resume-now";
}

export type TxMessage =
  | MicAudioData
  | MicAudioEnd
  | TextInput
  | InterruptSignal
  | PeriodicScreenshot
  | FrontendPlaybackComplete
  | CaptureContextResult
  | ResumeNow;

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

// ─── UI Command Messages (silent tool-call side-effects) ───

/**
 * Supervision state change — triggered by Agent tool calls:
 *   supervision.start  → { state: "active", duration, task }
 *   supervision.pause  → { state: "paused", pauseDuration, reason }
 *   supervision.resume → { state: "active" }
 *   session end        → { state: "completed" }
 */
export interface SupervisionStateChange {
  type: "supervision-state-change";
  state: SupervisionState;
  /** Total session duration in seconds (set on start) */
  duration?: number;
  /** Current task description (set on start or plan.update) */
  task?: string;
  /** Pause duration in seconds (set on pause) */
  pauseDuration?: number;
  /** Reason for state change */
  reason?: string;
}

/** Balance update — silent UI update (Agent delivers verbal feedback separately) */
export interface BalanceUpdate {
  type: "balance-update";
  balance: number;
  change: number;
  reason: string;
}

/**
 * Plan update — Agent called plan.update / plan.create tool.
 * Frontend renders this in a plan panel or overlay.
 */
export interface PlanUpdate {
  type: "plan-update";
  plan: PlanData;
}

export interface PlanTask {
  id: string;
  title: string;
  completed: boolean;
  estimatedMinutes?: number;
}

export interface PlanData {
  tasks: PlanTask[];
  totalMinutes: number;
  /** Suggested session duration derived from plan */
  suggestedDuration?: number;
}

/**
 * Tool call status — informs the frontend that the Agent is
 * executing a tool (shown as a subtle indicator, not disruptive).
 */
export interface ToolCallStatus {
  type: "tool-call-status";
  tool: string;
  status: "calling" | "success" | "error";
  /** Brief human-readable description (for devtools / debug) */
  message?: string;
}

/**
 * Supervision alert — soft = verbal reminder only (Agent speaks it),
 * hard = penalty applied (balance-update will follow).
 * The message field is for UI toast / indicator; the Agent also
 * verbalizes it separately.
 */
export interface SupervisionAlert {
  type: "supervision-alert";
  message: string;
  severity: "soft" | "hard";
  /** How many consecutive distractions in the current streak */
  streakCount?: number;
}

/** Timer sync from backend — keeps frontend timer in sync */
export interface TimerSync {
  type: "timer-sync";
  remainingSeconds: number;
  totalSeconds: number;
}

export interface ModelInfo {
  type: "model-info";
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
  payload?: {
    requestId?: string;
    prompt?: string;
    sources?: Array<"camera" | "screen">;
    reason?: string;
  };
}

export type RxMessage =
  | AudioMessage
  | AgentTextChunk
  | UserTranscript
  | AgentTextEnd
  | SupervisionStateChange
  | BalanceUpdate
  | PlanUpdate
  | ToolCallStatus
  | SupervisionAlert
  | TimerSync
  | ModelInfo
  | ControlMessage;
