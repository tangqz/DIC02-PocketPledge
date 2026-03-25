/* ────────────────────────────────────────────────
 *  StatusBar  –  Balance, Character, Timer
 *  Renders at the top of the Focus layout.
 * ──────────────────────────────────────────────── */
import { useEffect, useRef } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useCharacterStore } from "@/stores/characterStore";
import { useI18n } from "@/lib/i18n";
import { formatRmbFromCents, formatSignedRmbFromCents } from "@/lib/currency";
import { CHARACTER_MARKET } from "@/lib/modelConfig";

export default function StatusBar() {
  const {
    balance,
    lastBalanceChange,
    isConnected,
    supervisionState,
    timerSeconds,
    totalDuration,
    currentTask,
  } = useSessionStore();

  const selectedCharacterId = useCharacterStore((s) => s.selectedCharacterId);
  const characterName =
    CHARACTER_MARKET.find((c) => c.id === selectedCharacterId)?.displayName ??
    selectedCharacterId;

  const progress = totalDuration > 0 ? (totalDuration - timerSeconds) / totalDuration : 0;

  const fmt = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };
  const { t } = useI18n();

  // Animate balance changes
  const balanceRef = useRef<HTMLSpanElement>(null);
  const prevBalance = useRef(balance);

  useEffect(() => {
    if (balance !== prevBalance.current && balanceRef.current) {
      balanceRef.current.style.animation = "none";
      void balanceRef.current.offsetHeight;
      balanceRef.current.style.animation = "number-pop 0.3s ease-out";
    }
    prevBalance.current = balance;
  }, [balance]);

  const isDeducting = lastBalanceChange && lastBalanceChange.change < 0;

  return (
    <div className="grid grid-cols-3 items-center rounded-2xl bg-surface-elevated/60 px-5 py-3 backdrop-blur-lg">
      {/* Left: Timer */}
      <div className="flex items-center gap-3">
        {/* Connection dot */}
        <div
          className={`h-2 w-2 shrink-0 rounded-full ${isConnected ? "bg-success" : "bg-danger animate-breathing"}`}
          title={isConnected ? t("status.connected") : t("status.disconnected")}
        />
        {/* Mini progress ring */}
        <svg className="h-9 w-9 shrink-0 -rotate-90" viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="15" fill="none" className="stroke-slate-200" strokeWidth="3" />
          <circle
            cx="18" cy="18" r="15" fill="none"
            className="stroke-green-500 transition-all duration-1000"
            strokeWidth="3" strokeLinecap="round"
            strokeDasharray={`${progress * 94.25} 94.25`}
          />
        </svg>
        <div className="flex flex-col leading-tight">
          <span className="text-xs text-slate-400">{t("status.focusRemaining")}</span>
          <span className="font-mono text-xl font-semibold tabular-nums tracking-tight text-slate-800">
            {fmt(timerSeconds)}
          </span>
        </div>
      </div>

      {/* Center: Current task + state badge */}
      <div className="flex flex-col items-center gap-1 min-w-0 px-2">
        <span className="truncate text-sm font-semibold text-slate-700 max-w-full text-center">
          {currentTask || characterName}
        </span>
        <span
          className={`rounded-full px-3 py-0.5 text-xs font-medium ${
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

      {/* Right: Balance */}
      <div className="flex flex-col items-end leading-tight">
        <span className="text-xs text-slate-400">{t("status.balance")}</span>
        <div className="flex items-baseline gap-1.5">
          <span
            ref={balanceRef}
            className={`font-mono text-xl font-bold tabular-nums ${
              isDeducting ? "text-danger" : "text-success"
            }`}
          >
            {formatRmbFromCents(balance)}
          </span>
          {lastBalanceChange && (
            <span
              className={`text-xs font-medium ${
                lastBalanceChange.change < 0 ? "text-danger/70" : "text-success/70"
              }`}
            >
              {formatSignedRmbFromCents(lastBalanceChange.change)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
