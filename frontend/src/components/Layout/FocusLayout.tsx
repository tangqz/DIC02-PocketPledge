import { useCallback, useEffect, useRef } from "react";
import { useSend } from "@/App";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useI18n } from "@/lib/i18n";
import StatusBar from "@/components/SupervisionPanel/StatusBar";
import ChatPanel from "@/components/ChatPanel/ChatPanel";
import VoiceInput from "@/components/VoiceInput/VoiceInput";
import Live2DCanvas, { type Live2DCanvasHandle } from "@/components/Live2DCanvas/Live2DCanvas";
import MediaPreviewDock from "@/components/SupervisionPanel/MediaPreviewDock";

export default function FocusLayout() {
  const live2dRef = useRef<Live2DCanvasHandle>(null);
  const lastTapRef = useRef(0);
  const send = useSend();
  const { locale } = useI18n();

  const supervisionState = useSessionStore((s) => s.supervisionState);
  const timerSeconds = useSessionStore((s) => s.timerSeconds);
  const totalDuration = useSessionStore((s) => s.totalDuration);
  const pauseRemaining = useSessionStore((s) => s.pauseRemaining);
  const degradedMode = useSessionStore((s) => s.degradedMode);
  const activeToolCall = useSessionStore((s) => s.activeToolCall);
  const tickTimer = useSessionStore((s) => s.tickTimer);
  const tickPause = useSessionStore((s) => s.tickPause);

  const isPaused = supervisionState === "paused";

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (supervisionState === "active" && timerSeconds > 0) {
        tickTimer();
      }
      if (supervisionState === "paused" && (pauseRemaining ?? 0) > 0) {
        tickPause();
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [pauseRemaining, supervisionState, tickPause, tickTimer, timerSeconds]);

  const interruptAgentOutput = useCallback(() => {
    const chat = useChatStore.getState();
    const avatar = useAvatarStore.getState();
    const lastMessage = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1] : null;
    const shouldInterrupt = chat.isAgentSpeaking || avatar.pendingAudioMessages.length > 0 || Boolean(chat.streamingText);
    if (!shouldInterrupt) {
      return;
    }
    avatar.requestPlaybackInterrupt();
    avatar.clearAudioMessages();
    chat.clearStreaming();
    chat.setAgentSpeaking(false);
    send({ type: "interrupt-signal", text: chat.streamingText || lastMessage?.text || "" });
  }, [send]);

  const handleSendText = useCallback((text: string) => {
    interruptAgentOutput();
    useChatStore.getState().addMessage("user", text);
    send({ type: "text-input", text });
  }, [interruptAgentOutput, send]);

  const handleModelTapped = useCallback((hitArea: string) => {
    if (isPaused) return;
    const now = Date.now();
    if (now - lastTapRef.current < 5000) return; // throttle: 5s cooldown
    lastTapRef.current = now;
    const chat = useChatStore.getState();
    if (chat.isAgentSpeaking) return;
    const msg = hitArea === "Head" ? "[用户摸了摸你的头]" : "[用户戳了戳你]";
    send({ type: "text-input", text: msg });
  }, [isPaused, send]);

  return (
    <div className="relative flex h-full min-h-0 flex-col animate-fade-in">
      <div className="z-20 shrink-0 p-3">
        <StatusBar />
      </div>

      <div className="relative min-h-0 flex-1">
        <div id="live2d-container" className="absolute inset-0">
          {degradedMode ? <DowngradeTimerCard timerSeconds={timerSeconds} locale={locale} /> : <Live2DCanvas ref={live2dRef} onModelTapped={handleModelTapped} />}
        </div>

        {!degradedMode ? (
          <>
            <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
              <VoiceInput />
            </div>
            <MediaPreviewDock className="absolute bottom-4 right-4 z-20" />
          </>
        ) : null}

        {/* Countdown timer in top-left, below logout button */}
        <div className="absolute left-4 top-16 z-50 flex items-center gap-3 rounded-2xl bg-surface-elevated/90 px-4 py-3 shadow-lg backdrop-blur-lg">
          <svg className="h-10 w-10 -rotate-90" viewBox="0 0 36 36">
            <circle
              cx="18"
              cy="18"
              r="15"
              fill="none"
              className="stroke-white/20"
              strokeWidth="3"
            />
            <circle
              cx="18"
              cy="18"
              r="15"
              fill="none"
              className="stroke-green-500 transition-all duration-1000"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${(totalDuration > 0 ? 1 - timerSeconds / totalDuration : 0) * 94.25} 94.25`}
            />
          </svg>
          <div className="flex flex-col leading-tight">
            <span className="text-xs text-slate-500">{locale === "zh" ? "专注剩余" : "Focus time"}</span>
            <span className="font-mono text-xl font-semibold tabular-nums tracking-tight text-slate-800">
              {Math.floor(timerSeconds / 60)}:{String(timerSeconds % 60).padStart(2, "0")}
            </span>
          </div>
        </div>

        {activeToolCall ? (
          <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 rounded-full bg-accent/20 px-4 py-1.5 text-xs font-medium text-accent">
            {activeToolCall.tool}
          </div>
        ) : null}
      </div>

      <div className="h-[34%] min-h-[210px] border-t border-slate-200 bg-surface-elevated/60 backdrop-blur-lg">
        <ChatPanel expanded onSendText={handleSendText} disabled={isPaused} />
      </div>

      {isPaused && pauseRemaining !== undefined ? (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-slate-200/50 backdrop-blur-sm">
          <div className="min-w-72 rounded-3xl border border-slate-200 bg-surface-elevated/85 px-8 py-7 text-center">
            <p className="text-xs uppercase tracking-[0.35em] text-warning/70">{locale === "zh" ? "暂停中" : "Paused"}</p>
            <p className="mt-4 font-mono text-6xl font-semibold text-slate-800">
              {Math.floor(pauseRemaining / 60)}:{String(pauseRemaining % 60).padStart(2, "0")}
            </p>
            <button
              onClick={() => send({ type: "resume-now" })}
              className="mt-6 rounded-2xl bg-success/85 px-6 py-3 text-sm font-semibold text-slate-800 hover:bg-success"
            >
              {locale === "zh" ? "恢复专注" : "Resume Focus"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DowngradeTimerCard({ timerSeconds, locale }: { timerSeconds: number; locale: "zh" | "en" }) {
  const minutes = Math.floor(timerSeconds / 60);
  const seconds = String(timerSeconds % 60).padStart(2, "0");

  return (
    <div className="flex h-full items-center justify-center bg-slate-200/50 backdrop-blur-sm">
      <div className="min-w-72 rounded-3xl border border-slate-200 bg-surface-elevated/85 px-10 py-8 text-center shadow-2xl">
        <p className="text-xs uppercase tracking-[0.35em] text-slate-400">Basic Timer</p>
        <p className="mt-4 font-mono text-6xl font-semibold text-slate-800">
          {minutes}:{seconds}
        </p>
        <p className="mt-4 text-sm text-slate-500">
          {locale === "zh" ? "当前处于降级专注模式" : "Focus mode without avatar"}
        </p>
      </div>
    </div>
  );
}
