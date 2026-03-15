/* ────────────────────────────────────────────────
 *  StatusBar  –  Timer, Balance, Current Task
 *  Renders at the top of the Focus layout.
 * ──────────────────────────────────────────────── */
import { useEffect, useRef } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useI18n } from "@/lib/i18n";
import { formatRmbFromCents, formatSignedRmbFromCents } from "@/lib/currency";
import CharitySlider from "./CharitySlider";

/** Format seconds to MM:SS */
function fmt(s: number): string {
  const m = String(Math.floor(s / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return `${m}:${sec}`;
}

export default function StatusBar() {
  const {
    timerSeconds,
    totalDuration,
    balance,
    lastBalanceChange,
    currentTask,
    isConnected,
    supervisionState,
  } = useSessionStore();
  const { t } = useI18n();

  // Animate balance changes
  const balanceRef = useRef<HTMLSpanElement>(null);
  const prevBalance = useRef(balance);

  useEffect(() => {
    if (balance !== prevBalance.current && balanceRef.current) {
      balanceRef.current.style.animation = "none";
      // Trigger reflow
      void balanceRef.current.offsetHeight;
      balanceRef.current.style.animation = "number-pop 0.3s ease-out";
    }
    prevBalance.current = balance;
  }, [balance]);

  // Timer progress (0 → 1)
  const progress =
    totalDuration > 0 ? 1 - timerSeconds / totalDuration : 0;

  const isDeducting = lastBalanceChange && lastBalanceChange.change < 0;

  return (
    <div className="flex items-center gap-6 rounded-2xl bg-surface-elevated/60 px-5 py-3 backdrop-blur-lg">
      {/* Connection dot */}
      <div
        className={`h-2 w-2 rounded-full ${isConnected ? "bg-success" : "bg-danger animate-breathing"}`}
        title={isConnected ? t("status.connected") : t("status.disconnected")}
      />

      {/* Timer */}
      <div className="flex items-center gap-3">
        {/* Mini progress ring */}
        <svg className="h-9 w-9 -rotate-90" viewBox="0 0 36 36">
          <circle
            cx="18"
            cy="18"
            r="15"
            fill="none"
            className="stroke-white/10"
            strokeWidth="3"
          />
          <circle
            cx="18"
            cy="18"
            r="15"
            fill="none"
            className="stroke-accent transition-all duration-1000"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={`${progress * 94.25} 94.25`}
          />
        </svg>
        <span className="font-mono text-xl font-semibold tabular-nums tracking-tight">
          {fmt(timerSeconds)}
        </span>
      </div>

      {/* Divider */}
      <div className="h-6 w-px bg-slate-100" />

      {/* Balance */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">{t("status.balance")}</span>
          <span
            ref={balanceRef}
            className={`font-mono text-lg font-bold tabular-nums ${
              isDeducting ? "text-danger" : "text-success"
            }`}
          >
            {formatRmbFromCents(balance)}
          </span>
          {lastBalanceChange && (
            <span
              className={`text-xs font-medium ${
                lastBalanceChange.change < 0
                  ? "text-danger/70"
                  : "text-success/70"
              }`}
            >
              {formatSignedRmbFromCents(lastBalanceChange.change)}
            </span>
          )}
        </div>
        <CharitySlider />
      </div>

      {/* Divider */}
      <div className="h-6 w-px bg-slate-100" />

      {/* Task */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-slate-600">
          {currentTask || (t("status.state.setup"))}
        </p>
      </div>

      {/* State badge */}
      <span
        className={`rounded-full px-3 py-1 text-xs font-medium ${
          supervisionState === "active"
            ? "bg-success/20 text-success"
            : supervisionState === "paused"
              ? "bg-warning/20 text-warning"
              : supervisionState === "completed"
                ? "bg-slate-100 text-slate-500"
                : "bg-accent-soft text-accent"
        }`}
      >
        {supervisionState === "setup" && t("status.state.setup")}
        {supervisionState === "active" && t("status.state.active")}
        {supervisionState === "paused" && t("status.state.paused")}
        {supervisionState === "completed" && t("status.state.completed")}
      </span>
    </div>
  );
}
