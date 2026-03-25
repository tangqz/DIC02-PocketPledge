import { useCallback, useEffect, useRef } from "react";
import { useSend } from "@/App";
import { useSessionStore } from "@/stores/sessionStore";
import { useMediaStore } from "@/stores/mediaStore";
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
  const pauseRemaining = useSessionStore((s) => s.pauseRemaining);
  const degradedMode = useSessionStore((s) => s.degradedMode);
  const activeToolCall = useSessionStore((s) => s.activeToolCall);
  const tickTimer = useSessionStore((s) => s.tickTimer);
  const tickPause = useSessionStore((s) => s.tickPause);

  const isPaused = supervisionState === "paused";

  const screenGranted = useMediaStore((s) => s.screenGranted);
  const requestScreenShare = useMediaStore((s) => s.requestScreenShare);

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

        {activeToolCall ? (
          <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 rounded-full bg-accent/20 px-4 py-1.5 text-xs font-medium text-accent">
            {activeToolCall.tool}
          </div>
        ) : null}

        {/* Screen share re-auth banner after page refresh */}
        {!screenGranted && !degradedMode && (
          <div className="absolute right-4 top-4 z-40">
            <button
              onClick={() => void requestScreenShare()}
              className="flex items-center gap-2 rounded-xl bg-warning/90 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm hover:bg-warning"
            >
              <span>{locale === "zh" ? "重新开启屏幕共享" : "Re-enable Screen Share"}</span>
            </button>
          </div>
        )}
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
