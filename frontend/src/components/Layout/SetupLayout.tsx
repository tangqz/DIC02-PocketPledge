/* ────────────────────────────────────────────────
 *  SetupLayout  –  Chat-driven session setup
 *
 *  The user talks to the Agent to:
 *   1. Discuss and set a study plan
 *   2. Calibrate camera environment
 *   3. Agree on session duration & rules
 *
 *  The Agent calls tools (plan.update, supervision.start) which
 *  trigger state transitions via WS. The frontend never directly
 *  calls setSupervisionState("active").
 *
 *  Layout: Left = chat panel, Right = Live2D + overlaid status cards
 * ──────────────────────────────────────────────── */
import { useCallback, useRef } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useMediaStore } from "@/stores/mediaStore";
import { useSend } from "@/App";
import CameraPreview from "@/components/SupervisionPanel/CameraPreview";
import ChatPanel from "@/components/ChatPanel/ChatPanel";
import Live2DCanvas, {
  type Live2DCanvasHandle,
} from "@/components/Live2DCanvas/Live2DCanvas";
import VoiceInput from "@/components/VoiceInput/VoiceInput";
import { useI18n } from "@/lib/i18n";
import type { PlanData } from "@/lib/protocol";

export default function SetupLayout() {
  const { plan, balance, activeToolCall, degradedMode } = useSessionStore();
  const {
    cameraGranted,
    screenGranted,
    screenShareSupported,
    requestScreenShare,
    requestCamera,
    micGranted,
    micSupported,
    vadActive,
    micMuted,
    requestMicrophone,
  } = useMediaStore();
  const { t, locale, setLocale } = useI18n();
  const live2dRef = useRef<Live2DCanvasHandle>(null);
  const send = useSend();

  const handleSendText = useCallback((text: string) => {
    useChatStore.getState().addMessage("user", text);
    send({ type: "text-input", text });
  }, [send]);

  return (
    <div className="flex h-full animate-fade-in">
      {/* ── Left: Chat area (primary interaction) ── */}
      <div className="flex w-[45%] flex-shrink-0 flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-6 pb-2">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              {t("app.title")}
            </h1>
            <p className="mt-0.5 text-sm text-white/50">
              {t("setup.chatHint")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Tool-call indicator */}
            {activeToolCall && (
              <span className="flex items-center gap-1.5 rounded-full bg-accent/10 px-3 py-1 text-xs text-accent">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                {activeToolCall.tool}
              </span>
            )}
            {/* Locale toggle */}
            <button
              onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
              className="rounded-lg bg-surface-elevated/60 px-2.5 py-1 text-xs font-medium text-white/60 transition-colors hover:text-white"
            >
              {locale === "zh" ? "EN" : "中"}
            </button>
          </div>
        </div>

        {/* Chat panel — expanded mode with text input */}
        <div className="flex-1 overflow-hidden rounded-tr-2xl bg-surface-elevated/30 backdrop-blur-sm">
          <ChatPanel expanded onSendText={handleSendText} />
        </div>
      </div>

      {/* ── Right: Live2D stage + overlaid status cards ── */}
      <div className="relative flex-1">
        {/* Live2D canvas (fills the entire right area) */}
        <div id="live2d-container" className="absolute inset-0">
          {degradedMode ? <DowngradePanel /> : <Live2DCanvas ref={live2dRef} />}
        </div>

        {/* Voice input indicator — centered near bottom */}
        {!degradedMode && (
          <div className="absolute bottom-8 left-1/2 z-20 -translate-x-1/2">
            <VoiceInput />
          </div>
        )}

        {/* ── Overlaid status cards (bottom-left of the Live2D area) ── */}
        <div className="absolute bottom-6 left-6 z-10 flex max-w-xs flex-col gap-3">
          {/* Camera preview (compact) */}
          <div className="h-28 w-40 overflow-hidden rounded-xl bg-surface-elevated/80 shadow-lg backdrop-blur-md">
            <CameraPreview />
          </div>

          {/* Permissions & balance */}
          <div className="space-y-1.5 rounded-xl bg-surface-elevated/80 p-3 shadow-lg backdrop-blur-md">
            <PermissionRow
              label={t("setup.micLabel")}
              granted={micGranted}
              active={micGranted && vadActive && !micMuted && !degradedMode}
              required
              supported={micSupported}
              locale={locale}
              onRequest={
                !micGranted && micSupported
                  ? requestMicrophone
                  : undefined
              }
            />
            <PermissionRow
              label={t("setup.cameraLabel")}
              granted={cameraGranted}
              required
              locale={locale}
              onRequest={!cameraGranted ? requestCamera : undefined}
            />
            <PermissionRow
              label={t("setup.screenShare")}
              granted={screenGranted}
              supported={screenShareSupported}
              locale={locale}
              onRequest={!screenGranted && screenShareSupported ? requestScreenShare : undefined}
            />
            <div className="flex items-center justify-between text-sm">
              <span className="text-white/70">{t("status.balance")}</span>
              <span className="font-mono font-medium text-success">{balance}</span>
            </div>
          </div>
        </div>

        {/* ── Overlaid plan preview (bottom-right) ── */}
        <div className="absolute right-6 bottom-6 z-10 w-60">
          {plan ? (
            <PlanPreview plan={plan} locale={locale} />
          ) : (
            <div className="rounded-xl bg-surface-elevated/60 px-4 py-3 text-center text-xs text-white/40 shadow-lg backdrop-blur-md">
              {t("setup.agentStartHint")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DowngradePanel() {
  return (
    <div className="flex h-full items-center justify-center bg-black/35 backdrop-blur-sm">
      <div className="rounded-2xl border border-white/10 bg-surface-elevated/80 px-6 py-5 text-center shadow-lg">
        <p className="text-sm uppercase tracking-[0.3em] text-white/30">Fallback Mode</p>
        <p className="mt-3 text-lg font-semibold text-white/80">余额不足，陪伴模式已停用</p>
        <p className="mt-2 text-sm text-white/45">当前仅保留基础文本与状态同步能力。</p>
      </div>
    </div>
  );
}

/** Read-only plan preview card */
function PlanPreview({ plan, locale }: { plan: PlanData; locale: string }) {
  return (
    <div className="space-y-2 rounded-xl bg-surface-elevated/50 p-4">
      <h3 className="text-sm font-medium text-white/60">
        {locale === "zh" ? "学习计划" : "Study Plan"}
      </h3>
      <div className="space-y-1.5">
        {plan.tasks.map((task) => (
          <div key={task.id} className="flex items-center gap-2 text-sm">
            <span
              className={`h-4 w-4 rounded border text-center text-xs leading-4 ${
                task.completed
                  ? "border-success bg-success/20 text-success"
                  : "border-white/20 text-transparent"
              }`}
            >
              ✓
            </span>
            <span
              className={`flex-1 ${task.completed ? "text-white/40 line-through" : "text-white/80"}`}
            >
              {task.title}
            </span>
            {task.estimatedMinutes && (
              <span className="text-xs text-white/30">
                {task.estimatedMinutes}m
              </span>
            )}
          </div>
        ))}
      </div>
      {plan.suggestedDuration && (
        <p className="mt-2 text-xs text-white/40">
          {locale === "zh"
            ? `建议时长: ${plan.suggestedDuration / 60} 分钟`
            : `Suggested: ${plan.suggestedDuration / 60} min`}
        </p>
      )}
    </div>
  );
}

function PermissionRow({
  label,
  granted,
  active = false,
  required,
  supported = true,
  locale = "zh",
  onRequest,
}: {
  label: string;
  granted: boolean;
  active?: boolean;
  required?: boolean;
  supported?: boolean;
  locale?: string;
  /** If provided, the status badge becomes a clickable button to request permission */
  onRequest?: () => void;
}) {
  const statusContent = !supported ? (
    <span className="text-white/30">
      {locale === "zh" ? "不支持" : "Not Supported"}
    </span>
  ) : active ? (
    <span className="text-accent">
      ● {locale === "zh" ? "正在使用" : "In Use"}
    </span>
  ) : granted ? (
    <span className="text-success">
      ✓ {locale === "zh" ? "已授权" : "Authorized"}
    </span>
  ) : onRequest ? (
    <button
      onClick={onRequest}
      className="rounded-md bg-accent/20 px-2 py-0.5 text-accent transition-colors hover:bg-accent/30"
    >
      {locale === "zh" ? "点击授权" : "Authorize"}
    </button>
  ) : (
    <span className="text-warning">
      {locale === "zh" ? "待授权" : "Pending"}
    </span>
  );

  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-white/70">
        {label}
        {required && <span className="ml-1 text-danger">*</span>}
      </span>
      {statusContent}
    </div>
  );
}
