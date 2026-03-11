import { useCallback, useEffect, useRef, useState } from "react";
import { useSend } from "@/App";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useMediaStore } from "@/stores/mediaStore";
import { useAuthStore } from "@/stores/authStore";
import { useI18n } from "@/lib/i18n";
import { formatRmbFromCents, formatSignedRmbFromCents } from "@/lib/currency";
import ChatPanel from "@/components/ChatPanel/ChatPanel";
import VoiceInput from "@/components/VoiceInput/VoiceInput";
import Live2DCanvas, { type Live2DCanvasHandle } from "@/components/Live2DCanvas/Live2DCanvas";
import DailyPlanCalendar from "@/components/Dashboard/DailyPlanCalendar";
import CharacterMarket from "@/components/Dashboard/CharacterMarket";

export default function SetupLayout() {
  const live2dRef = useRef<Live2DCanvasHandle>(null);
  const send = useSend();
  const { t, locale, setLocale } = useI18n();
  const token = useAuthStore((s) => s.token);
  const currentUserId = useAuthStore((s) => s.user?.user_id);

  const [sessionSummaries, setSessionSummaries] = useState<Array<{ id: string; summary_text: string; created_at: string }>>([]);
  const [transactions, setTransactions] = useState<Array<{ id: string; amount: number; reason: string; created_at: string; tx_type: string; from_user_id?: number | null; to_user_id?: number | null }>>([]);

  const plan = useSessionStore((s) => s.plan);
  const balance = useSessionStore((s) => s.balance);
  const activeToolCall = useSessionStore((s) => s.activeToolCall);
  const degradedMode = useSessionStore((s) => s.degradedMode);

  const micGranted = useMediaStore((s) => s.micGranted);
  const cameraGranted = useMediaStore((s) => s.cameraGranted);
  const screenGranted = useMediaStore((s) => s.screenGranted);
  const requestMicrophone = useMediaStore((s) => s.requestMicrophone);
  const requestCamera = useMediaStore((s) => s.requestCamera);
  const requestScreenShare = useMediaStore((s) => s.requestScreenShare);
  const snapshotInterval = useMediaStore((s) => s.snapshotInterval);
  const setSnapshotInterval = useMediaStore((s) => s.setSnapshotInterval);

  useEffect(() => {
    const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:12393";
    if (!token) {
      return;
    }
    const headers = { Authorization: `Bearer ${token}` };
    void Promise.all([
      fetch(`${API_BASE}/api/business/me/session-summaries?limit=6`, { headers }).then((r) => r.json()).catch(() => ({ items: [] })),
      fetch(`${API_BASE}/api/business/me/transactions?limit=8`, { headers }).then((r) => r.json()).catch(() => ({ items: [] })),
    ]).then(([summaryData, txData]) => {
      setSessionSummaries(Array.isArray(summaryData?.items) ? summaryData.items : []);
      setTransactions(Array.isArray(txData?.items) ? txData.items : []);
    });
  }, [token]);

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

  const handleSwitchCharacter = useCallback((_characterId: string) => {
    useChatStore.getState().clearMessages();
    useAvatarStore.getState().clearAudioMessages();
  }, []);

  const getSignedAmount = useCallback((item: { amount: number; from_user_id?: number | null; to_user_id?: number | null }) => {
    if (!currentUserId) {
      return item.amount;
    }
    if (item.from_user_id === currentUserId && item.to_user_id !== currentUserId) {
      return -Math.abs(item.amount);
    }
    if (item.to_user_id === currentUserId && item.from_user_id !== currentUserId) {
      return Math.abs(item.amount);
    }
    return item.amount;
  }, [currentUserId]);

  return (
    <div className="flex h-full min-h-0 animate-fade-in">
      <aside className="flex w-[48%] min-w-[360px] flex-col gap-3 overflow-y-auto border-r border-slate-200 bg-slate-50/55 p-4">
        <div className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-800">{t("app.title")}</h1>
            <p className="mt-1 text-sm text-slate-500">{t("setup.chatHint")}</p>
          </div>
          <button
            onClick={() => {
              const nextLocale = locale === "zh" ? "en" : "zh";
              setLocale(nextLocale);
              send({ type: "set-locale", locale: nextLocale });
            }}
            className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200"
          >
            {locale === "zh" ? "EN" : "中"}
          </button>
        </div>

        <DailyPlanCalendar plan={plan} />

        <section className="rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4 backdrop-blur-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            {locale === "zh" ? "监督准备" : "Supervision Setup"}
          </h3>
          <div className="space-y-2 text-sm">
            <PermissionRow label={locale === "zh" ? "麦克风" : "Microphone"} granted={micGranted} onRequest={requestMicrophone} />
            <PermissionRow label={locale === "zh" ? "摄像头" : "Camera"} granted={cameraGranted} onRequest={requestCamera} />
            <PermissionRow label={locale === "zh" ? "屏幕共享" : "Screen Share"} granted={screenGranted} onRequest={requestScreenShare} />
            <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
              <span className="text-slate-600">{t("status.balance")}</span>
              <span className="font-mono text-success">{formatRmbFromCents(balance)}</span>
            </div>
            <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-slate-600">
                  {locale === "zh" ? "监督流请求频率(秒)" : "Supervision Stream Interval (s)"}
                </span>
                <input
                  type="number"
                  min={5}
                  max={300}
                  value={snapshotInterval}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    const clamped = Number.isFinite(next) ? Math.max(5, Math.min(300, Math.round(next))) : 20;
                    setSnapshotInterval(clamped);
                  }}
                  className="w-20 rounded bg-slate-100 px-2 py-1 text-right font-mono text-slate-800 outline-none"
                />
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                {locale === "zh"
                  ? "仅在非专注模式可调整，用于临时演示调试。"
                  : "Editable in non-focus mode for temporary demo tuning."}
              </p>
            </div>
          </div>
        </section>

        <CharacterMarket onSwitch={handleSwitchCharacter} />

        <section className="rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4 backdrop-blur-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            {locale === "zh" ? "过去专注记录" : "Past Focus Records"}
          </h3>
          <div className="space-y-2 text-xs">
            {sessionSummaries.length === 0 ? (
              <p className="text-slate-500">{locale === "zh" ? "暂无历史记录" : "No records yet"}</p>
            ) : sessionSummaries.map((item) => (
              <div key={item.id} className="rounded-lg bg-slate-50 p-2 text-slate-600">
                <p>{item.summary_text}</p>
                <p className="mt-1 text-[11px] text-slate-400">{new Date(item.created_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4 backdrop-blur-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            {locale === "zh" ? "资金记录" : "Fund Records"}
          </h3>
          <div className="space-y-2 text-xs">
            {transactions.length === 0 ? (
              <p className="text-slate-500">{locale === "zh" ? "暂无资金流水" : "No transactions yet"}</p>
            ) : transactions.map((item) => {
              const signedAmount = getSignedAmount(item);
              return (
              <div key={item.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-2 py-1.5 text-slate-600">
                <div>
                  <p>{item.reason}</p>
                  <p className="text-[11px] text-slate-400">{new Date(item.created_at).toLocaleDateString()} · {item.tx_type}</p>
                </div>
                <span className={`font-mono ${signedAmount >= 0 ? "text-success" : "text-danger"}`}>
                  {formatSignedRmbFromCents(signedAmount)}
                </span>
              </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4 text-xs text-slate-500 backdrop-blur-sm">
          {locale === "zh"
            ? "提示：切换角色会立即热切换模型，并清空聊天记录以保证人设一致性。"
            : "Tip: Switching character hot-loads the model and clears chat history to keep persona consistency."}
        </section>
      </aside>

      <main className="relative flex flex-1 min-w-0 flex-col bg-gradient-to-b from-surface/20 to-transparent">
        <div className="relative min-h-0 flex-1">
          <div id="live2d-container" className="absolute inset-0">
            {degradedMode ? <DowngradePanel locale={locale} /> : <Live2DCanvas ref={live2dRef} />}
          </div>

          {!degradedMode ? (
            <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
              <VoiceInput />
            </div>
          ) : null}

          {activeToolCall ? (
            <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2 rounded-full bg-accent/20 px-4 py-1.5 text-xs font-medium text-accent">
              {activeToolCall.tool}
            </div>
          ) : null}
        </div>

        <div className="h-[36%] min-h-[220px] border-t border-slate-200 bg-surface-elevated/55 backdrop-blur-lg">
          <ChatPanel expanded onSendText={handleSendText} />
        </div>
      </main>
    </div>
  );
}

function PermissionRow({
  label,
  granted,
  onRequest,
}: {
  label: string;
  granted: boolean;
  onRequest: () => Promise<boolean>;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
      <span className="text-slate-600">{label}</span>
      {granted ? (
        <span className="text-success">Ready</span>
      ) : (
        <button className="rounded bg-accent/25 px-2 py-0.5 text-accent hover:bg-accent/35" onClick={() => void onRequest()}>
          Authorize
        </button>
      )}
    </div>
  );
}

function DowngradePanel({ locale }: { locale: "zh" | "en" }) {
  return (
    <div className="flex h-full items-center justify-center bg-slate-200/50 backdrop-blur-sm">
      <div className="rounded-2xl border border-slate-200 bg-surface-elevated/80 px-6 py-5 text-center shadow-lg">
        <p className="text-sm uppercase tracking-[0.3em] text-slate-400">Fallback Mode</p>
        <p className="mt-3 text-lg font-semibold text-slate-700">
          {locale === "zh" ? "余额不足，陪伴模式已停用" : "Balance exhausted. Companion mode is disabled."}
        </p>
      </div>
    </div>
  );
}
