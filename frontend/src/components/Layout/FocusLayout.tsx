/* ────────────────────────────────────────────────
 *  FocusLayout  –  Main study view with Live2D + status + subtitles
 *
 *  Key design: ALL state transitions come from the backend.
 *  - Pause: user requests via chat → Agent negotiates → Agent calls
 *    supervision.pause(duration) → backend sends state-change.
 *  - The pause FAB now opens the chat panel and sends a pause-intent
 *    message, rather than directly toggling state.
 *  - Timer countdown runs locally but is periodically synced by
 *    timer-sync messages from backend.
 * ──────────────────────────────────────────────── */
import { useEffect, useRef, useCallback, useState } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useSend } from "@/App";
import StatusBar from "@/components/SupervisionPanel/StatusBar";
import ChatPanel from "@/components/ChatPanel/ChatPanel";
import VoiceInput from "@/components/VoiceInput/VoiceInput";
import Live2DCanvas, {
  type Live2DCanvasHandle,
} from "@/components/Live2DCanvas/Live2DCanvas";
import { useI18n } from "@/lib/i18n";

export default function FocusLayout() {
  const {
    supervisionState,
    tickTimer,
    timerSeconds,
    pauseRemaining,
    tickPause,
    lastAlert,
    degradedMode,
  } = useSessionStore();
  const isPaused = supervisionState === "paused";
  const live2dRef = useRef<Live2DCanvasHandle>(null);
  const { t, locale } = useI18n();
  const send = useSend();

  // Whether the chat panel is open (user can open it to talk to Agent)
  const [chatOpen, setChatOpen] = useState(false);

  // ── Timer tick (active state only) ──
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(
    undefined,
  );

  useEffect(() => {
    if (supervisionState === "active" && timerSeconds > 0) {
      timerRef.current = setInterval(() => {
        tickTimer();
      }, 1000);
    }
    return () => clearInterval(timerRef.current);
  }, [supervisionState, timerSeconds > 0, tickTimer]);

  // ── Pause countdown tick ──
  const pauseTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(
    undefined,
  );

  useEffect(() => {
    if (isPaused && pauseRemaining !== undefined && pauseRemaining > 0) {
      pauseTimerRef.current = setInterval(() => {
        tickPause();
      }, 1000);
    }
    return () => clearInterval(pauseTimerRef.current);
  }, [isPaused, pauseRemaining, tickPause]);

  // ── Flash alert indicator briefly ──
  const [alertFlash, setAlertFlash] = useState(false);
  useEffect(() => {
    if (lastAlert) {
      setAlertFlash(true);
      const t = setTimeout(() => setAlertFlash(false), 2000);
      return () => clearTimeout(t);
    }
  }, [lastAlert]);

  const handleSendText = useCallback((text: string) => {
    useChatStore.getState().addMessage("user", text);
    send({ type: "text-input", text });
  }, [send]);

  /**
   * Pause request: instead of directly toggling state, open the chat
   * and send a message expressing the user's intent to pause.
   * The Agent will negotiate (e.g., "how long?", "why?") then call
   * supervision.pause(duration, reason) if approved.
   */
  const handlePauseRequest = () => {
    if (supervisionState === "active") {
      setChatOpen(true);
      // Send an automatic intent message so the Agent knows what the user wants
      const pauseMsg =
        locale === "zh"
          ? "我想暂停一下，休息一会儿"
          : "I'd like to take a break";
      useChatStore.getState().addMessage("user", pauseMsg);
      send({ type: "text-input", text: pauseMsg });
    } else if (isPaused) {
      // When paused, tapping the button sends a resume-intent message
      const resumeMsg =
        locale === "zh" ? "我准备好了，继续吧" : "I'm ready, let's continue";
      useChatStore.getState().addMessage("user", resumeMsg);
      send({ type: "text-input", text: resumeMsg });
    }
  };

  const handleEndSession = useCallback(() => {
    send({
      type: "text-input",
      text: locale === "zh" ? "结束本次监督" : "End this session",
    });
  }, [locale, send]);

  return (
    <div className="relative flex h-full flex-col animate-fade-in">
      {/* Top bar */}
      <div className="shrink-0 p-4">
        <StatusBar />
      </div>

      {/* Main area: Live2D (right) + Side panel (left) */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel – chat (expanded when paused or user opens it) */}
        <div
          className={`flex flex-col transition-all duration-500 ${
            isPaused || chatOpen ? "w-1/2" : "w-0 opacity-0"
          }`}
        >
          {(isPaused || chatOpen) && (
            <div className="relative h-full rounded-tr-2xl bg-surface-elevated/40 backdrop-blur-lg">
              {/* Close chat button (only when not paused — paused always shows chat) */}
              {!isPaused && chatOpen && (
                <button
                  onClick={() => setChatOpen(false)}
                  className="absolute right-3 top-3 z-20 rounded-full bg-surface-elevated/60 p-1.5 text-white/40 hover:text-white"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
              <ChatPanel expanded onSendText={handleSendText} />
            </div>
          )}
        </div>

        {/* Right panel – Live2D stage */}
        <div className="relative flex-1">
          {/* Live2D canvas */}
          <div id="live2d-container" className="absolute inset-0">
            {degradedMode ? (
              <DowngradeTimerCard
                timerSeconds={timerSeconds}
                locale={locale}
                isPaused={isPaused}
                onEndSession={handleEndSession}
              />
            ) : (
              <Live2DCanvas ref={live2dRef} />
            )}
          </div>

          {/* Alert flash overlay */}
          {alertFlash && lastAlert && (
            <div
              className={`pointer-events-none absolute inset-0 transition-opacity duration-500 ${
                lastAlert.severity === "hard"
                  ? "bg-danger/10"
                  : "bg-warning/10"
              }`}
            />
          )}

          {/* Voice input indicator */}
          {!degradedMode && (
            <div className="absolute bottom-24 left-1/2 -translate-x-1/2">
              <VoiceInput />
            </div>
          )}

          {/* Pause remaining indicator */}
          {isPaused && pauseRemaining !== undefined && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 rounded-full bg-warning/20 px-4 py-1.5 text-sm font-medium text-warning backdrop-blur-md">
              {locale === "zh" ? "暂停剩余: " : "Break: "}
              {Math.floor(pauseRemaining / 60)}:
              {String(pauseRemaining % 60).padStart(2, "0")}
            </div>
          )}
        </div>
      </div>

      {/* Bottom subtitle bar (always visible in focus mode) */}
      <div className="absolute inset-x-0 bottom-0">
        <ChatPanel />
      </div>

      {/* Action buttons (bottom-right) */}
      <div className="absolute right-6 bottom-20 z-30 flex flex-col gap-3">
        {/* Open chat FAB (when chat is hidden & not paused) */}
        {!isPaused && !chatOpen && (
          <button
            onClick={() => setChatOpen(true)}
            className="rounded-full bg-surface-elevated/80 p-3 backdrop-blur-md transition-all hover:scale-110 active:scale-95"
            title={t("focus.openChat")}
          >
            <svg
              className="h-6 w-6 text-white/60"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </button>
        )}

        {/* Pause / Resume FAB */}
        <button
          onClick={handlePauseRequest}
          className="rounded-full bg-surface-elevated/80 p-3 backdrop-blur-md transition-all hover:scale-110 active:scale-95"
          title={isPaused ? t("focus.resume") : t("focus.pause")}
        >
          {isPaused ? (
            <svg
              className="h-6 w-6 text-success"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M8 5v14l11-7z" />
            </svg>
          ) : (
            <svg
              className="h-6 w-6 text-warning"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
            </svg>
          )}
        </button>
      </div>

      {/* Pause overlay */}
      {isPaused && (
        <div className="pointer-events-none absolute inset-0 z-10 bg-black/30 backdrop-blur-sm" />
      )}
    </div>
  );
}

function DowngradeTimerCard({
  timerSeconds,
  locale,
  isPaused,
  onEndSession,
}: {
  timerSeconds: number;
  locale: string;
  isPaused: boolean;
  onEndSession: () => void;
}) {
  const minutes = Math.floor(timerSeconds / 60);
  const seconds = String(timerSeconds % 60).padStart(2, "0");

  return (
    <div className="flex h-full items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="min-w-72 rounded-3xl border border-white/10 bg-surface-elevated/85 px-10 py-8 text-center shadow-2xl">
        <p className="text-xs uppercase tracking-[0.35em] text-white/30">Basic Timer</p>
        <p className="mt-4 font-mono text-6xl font-semibold text-white/88">
          {minutes}:{seconds}
        </p>
        <p className="mt-4 text-sm text-white/45">
          {locale === "zh"
            ? isPaused
              ? "当前处于降级暂停模式"
              : "当前处于降级专注模式"
            : isPaused
              ? "Paused in fallback mode"
              : "Focus mode without avatar"}
        </p>
        <button
          onClick={onEndSession}
          className="mt-6 rounded-xl bg-danger/80 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-danger"
        >
          {locale === "zh" ? "结束本次监督" : "End Session"}
        </button>
      </div>
    </div>
  );
}
