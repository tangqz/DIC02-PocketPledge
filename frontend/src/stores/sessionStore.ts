/* ────────────────────────────────────────────────
 *  Session Store  –  supervision state, timer, balance, plan
 *
 *  Design: The frontend NEVER directly transitions supervision
 *  state. All transitions come from the backend (Agent tool calls
 *  or server-side events) via WebSocket RxMessages.
 *
 *  The only write paths are:
 *    • dispatch() in useWebSocket — processes supervision-state-change,
 *      balance-update, plan-update, timer-sync, supervision-alert
 *    • tickTimer() — local 1-second countdown (synced by timer-sync)
 * ──────────────────────────────────────────────── */
import { create } from "zustand";
import type {
  SupervisionState,
  PlanData,
  PlanTask,
} from "@/lib/protocol";

export interface BalanceEvent {
  change: number;
  reason: string;
  timestamp: number;
}

export interface AlertEvent {
  message: string;
  severity: "soft" | "hard";
  streakCount?: number;
  timestamp: number;
}

interface SessionState {
  // ── Core state ──
  supervisionState: SupervisionState;
  balance: number;
  degradedMode: boolean;
  timerSeconds: number; // remaining seconds
  totalDuration: number; // total session duration in seconds
  currentTask: string;
  isConnected: boolean;
  /** Seconds remaining for a negotiated pause (undefined when not paused) */
  pauseRemaining: number | undefined;
  pauseReason: string;

  // ── Plan ──
  plan: PlanData | null;

  // ── Balance history (for Summary panel) ──
  balanceHistory: BalanceEvent[];
  lastBalanceChange: BalanceEvent | null;

  // ── Alerts ──
  alerts: AlertEvent[];
  lastAlert: AlertEvent | null;

  // ── Tool call indicator ──
  activeToolCall: { tool: string; status: string } | null;

  // ── Actions (called only by WS dispatcher) ──
  /** Apply a supervision-state-change from the backend */
  applyStateChange: (
    next: SupervisionState,
    opts?: {
      duration?: number;
      task?: string;
      pauseDuration?: number;
      reason?: string;
    },
  ) => void;

  /** Apply a balance-update from the backend */
  applyBalanceUpdate: (balance: number, change: number, reason: string) => void;

  /** Apply a plan-update from the backend */
  applyPlanUpdate: (plan: PlanData) => void;

  /** Apply a timer-sync from the backend */
  applyTimerSync: (remaining: number, total: number) => void;

  /** Apply a supervision-alert from the backend */
  applyAlert: (message: string, severity: "soft" | "hard", streakCount?: number) => void;

  /** Tool call indicator */
  setActiveToolCall: (tc: { tool: string; status: string } | null) => void;

  setBalance: (balance: number) => void;
  setDegradedMode: (degraded: boolean) => void;

  /** Local timer tick (1s interval) */
  tickTimer: () => void;
  /** Tick the pause countdown (1s interval) */
  tickPause: () => void;

  setIsConnected: (connected: boolean) => void;

  /** Toggle a plan task completed locally (optimistic; confirmed by next plan-update) */
  togglePlanTask: (taskId: string) => void;

  /** Full reset (used on session restart from Summary) */
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  supervisionState: "setup",
  balance: 3000,
  degradedMode: false,
  timerSeconds: 0,
  totalDuration: 0,
  currentTask: "",
  isConnected: false,
  pauseRemaining: undefined,
  pauseReason: "",
  plan: null,
  balanceHistory: [],
  lastBalanceChange: null,
  alerts: [],
  lastAlert: null,
  activeToolCall: null,

  // ── State change (from backend only) ──
  applyStateChange: (next, opts = {}) => {
    const current = get().supervisionState;
    console.log(`[Session] State: ${current} → ${next}`, opts);

    const patch: Partial<SessionState> = { supervisionState: next };

    if (next === "active" && opts.duration !== undefined) {
      patch.timerSeconds = opts.duration;
      patch.totalDuration = opts.duration;
      patch.degradedMode = false;
    }
    if (next === "setup") {
      patch.degradedMode = false;
    }
    if (next === "active") {
      patch.pauseRemaining = undefined;
      patch.pauseReason = "";
    }
    if (opts.task !== undefined) {
      patch.currentTask = opts.task;
    }
    if (next === "paused") {
      patch.pauseRemaining = opts.pauseDuration ?? undefined;
      patch.pauseReason = opts.reason ?? "";
    }
    set(patch as any);
  },

  applyBalanceUpdate: (balance, change, reason) => {
    const event: BalanceEvent = { change, reason, timestamp: Date.now() };
    set({
      balance,
      degradedMode: balance <= 0 ? get().degradedMode : false,
      balanceHistory: [...get().balanceHistory, event],
      lastBalanceChange: event,
    });
  },

  applyPlanUpdate: (plan) => set({ plan }),

  applyTimerSync: (remaining, total) =>
    set({ timerSeconds: remaining, totalDuration: total }),

  applyAlert: (message, severity, streakCount) => {
    const event: AlertEvent = {
      message,
      severity,
      streakCount,
      timestamp: Date.now(),
    };
    set({
      alerts: [...get().alerts, event],
      lastAlert: event,
    });
  },

  setActiveToolCall: (tc) => set({ activeToolCall: tc }),

  setBalance: (balance) => set({ balance }),
  setDegradedMode: (degradedMode) => set({ degradedMode }),

  tickTimer: () => {
    set((s) => ({
      timerSeconds: Math.max(0, s.timerSeconds - 1),
    }));
  },

  tickPause: () => {
    const pr = get().pauseRemaining;
    if (pr !== undefined && pr > 0) {
      set({ pauseRemaining: pr - 1 });
    }
    // Note: when pauseRemaining hits 0, the backend will send a
    // supervision-state-change → "active" and/or the Agent will
    // verbally tell the user pause time is up.
  },

  setIsConnected: (connected) => set({ isConnected: connected }),

  togglePlanTask: (taskId) => {
    const plan = get().plan;
    if (!plan) return;
    const tasks = plan.tasks.map((t: PlanTask) =>
      t.id === taskId ? { ...t, completed: !t.completed } : t,
    );
    set({ plan: { ...plan, tasks } });
  },

  reset: () =>
    set({
      supervisionState: "setup",
      balance: 3000,
      degradedMode: false,
      timerSeconds: 0,
      totalDuration: 0,
      currentTask: "",
      isConnected: false,
      pauseRemaining: undefined,
      pauseReason: "",
      plan: null,
      balanceHistory: [],
      lastBalanceChange: null,
      alerts: [],
      lastAlert: null,
      activeToolCall: null,
    }),
}));
