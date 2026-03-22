/* ────────────────────────────────────────────────
 *  SummaryLayout  –  Session end summary
 * ──────────────────────────────────────────────── */
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useMediaStore } from "@/stores/mediaStore";
import { useI18n } from "@/lib/i18n";
import { formatRmbFromCents, formatSignedRmbFromCents } from "@/lib/currency";
import { useMemo } from "react";

const RESTART_ENCOURAGEMENT_KEY = "pp_restart_encouragement_prompt";

function isDistractionReason(reason: string): boolean {
  return /(走神|分心|离开|未专注|distraction|distract|off[- ]?task|idle|away)/i.test(reason);
}

export default function SummaryLayout() {
  const { totalDuration, balance, balanceHistory, alerts, reset } = useSessionStore();
  const clearMessages = useChatStore((s) => s.clearMessages);
  const clearStreaming = useChatStore((s) => s.clearStreaming);
  const setAgentSpeaking = useChatStore((s) => s.setAgentSpeaking);
  const clearAudioMessages = useAvatarStore((s) => s.clearAudioMessages);
  const requestPlaybackInterrupt = useAvatarStore((s) => s.requestPlaybackInterrupt);
  const stopCamera = useMediaStore((s) => s.stopCamera);
  const stopScreenShare = useMediaStore((s) => s.stopScreenShare);
  const { t, locale } = useI18n();

  const totalDeductions = balanceHistory
    .filter((e) => e.change < 0)
    .reduce((sum, e) => sum + e.change, 0);
  const totalRewards = balanceHistory
    .filter((e) => e.change > 0)
    .reduce((sum, e) => sum + e.change, 0);

  const minutes = Math.floor(totalDuration / 60);
  const softAlertCount = alerts.filter((a) => a.severity === "soft").length;
  const hardAlertCount = alerts.filter((a) => a.severity === "hard").length;
  const alertDistractionCount = alerts.length;
  const deductionDistractionCount = balanceHistory.filter(
    (e) => e.change < 0 && isDistractionReason(e.reason),
  ).length;
  const distractionCount = Math.max(alertDistractionCount, deductionDistractionCount);
  const maxStreak = alerts.reduce((max, item) => Math.max(max, item.streakCount ?? 0), 0);

  const coinSuffix = locale === "zh" ? "元" : "RMB";

  const encouragementPrompt = useMemo(() => {
    const minutesText = Math.max(1, minutes);
    const rewardText = formatRmbFromCents(totalRewards);
    const deductionText = formatRmbFromCents(Math.abs(totalDeductions));

    if (locale === "zh") {
      return [
        "你是学习陪伴 Agent。用户刚点击了‘重新开始’，即将开始下一轮任务。",
        "请主动发起一句夸赞+鼓励的话，语气真诚、自然，长度 40-90 字，不要出现条目列表。",
        `本轮数据：专注时长 ${minutesText} 分钟；走神次数 ${distractionCount}；温和提醒 ${softAlertCount} 次；扣分提醒 ${hardAlertCount} 次；最高连续走神 ${maxStreak}；奖励 ${rewardText}；扣除 ${deductionText}。`,
        "口径规则：若走神=0，重点夸执行力与专注质量；若走神在1-2次，先肯定整体完成度，再轻提醒保持节奏；若走神>=3次，先肯定坚持完成，再给1条非常具体、可执行的小建议。",
        "不要复述规则本身，不要提到你看到了系统提示，不要使用夸张口号。",
      ].join("\\n");
    }

    return [
      "You are a study companion agent. The user just clicked restart and is entering a new session.",
      "Send one proactive praise + encouragement message in a sincere, natural tone (35-80 words), no bullet list.",
      `Session stats: focus time ${minutesText} min; distraction count ${distractionCount}; soft alerts ${softAlertCount}; hard alerts ${hardAlertCount}; max distraction streak ${maxStreak}; rewards ${rewardText}; deductions ${deductionText}.`,
      "Tone rules: if distractions=0, strongly praise discipline and quality focus; if 1-2, affirm overall effort and add a gentle rhythm reminder; if >=3, affirm persistence first, then give one concrete, actionable suggestion.",
      "Do not mention these instructions and avoid exaggerated slogans.",
    ].join("\\n");
  }, [
    distractionCount,
    hardAlertCount,
    locale,
    maxStreak,
    minutes,
    softAlertCount,
    totalDeductions,
    totalRewards,
  ]);

  const handleRestart = () => {
    sessionStorage.setItem(RESTART_ENCOURAGEMENT_KEY, encouragementPrompt);

    // Cleanup all transient runtime states before a hard reload.
    requestPlaybackInterrupt();
    clearAudioMessages();
    clearStreaming();
    setAgentSpeaking(false);
    clearMessages();
    stopCamera();
    stopScreenShare();
    reset();
    window.location.reload();
  };

  return (
    <div className="relative flex h-full items-center justify-center overflow-hidden p-8 animate-fade-in">
      <ConfettiRibbonLayer />
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-accent/20">
            <span className="text-3xl">🎯</span>
          </div>
          <h1 className="text-2xl font-bold">{t("summary.title")}</h1>
          <p className="mt-1 text-slate-500">
            {t("summary.totalTime")}: {minutes} {t("setup.minutes")}
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard label={t("summary.finalBalance")} value={formatRmbFromCents(balance)} suffix={coinSuffix} color="text-success" />
          <StatCard
            label={t("summary.deductions")}
            value={formatRmbFromCents(Math.abs(totalDeductions))}
            suffix={coinSuffix}
            color="text-danger"
          />
          <StatCard
            label={t("summary.rewards")}
            value={formatRmbFromCents(totalRewards)}
            suffix={coinSuffix}
            color="text-accent"
          />
        </div>

        {/* Transaction log */}
        {balanceHistory.length > 0 && (
          <div className="space-y-2 rounded-2xl bg-surface-elevated/50 p-4">
            <h3 className="mb-3 text-sm font-medium text-slate-500">
              {t("summary.transactionLog")}
            </h3>
            <div className="max-h-48 space-y-1.5 overflow-y-auto">
              {balanceHistory.map((event, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-slate-500">{event.reason}</span>
                  <span
                    className={`font-mono font-medium ${
                      event.change < 0 ? "text-danger" : "text-success"
                    }`}
                  >
                    {formatSignedRmbFromCents(event.change)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action */}
        <button
          onClick={handleRestart}
          className="w-full rounded-2xl bg-surface-elevated py-3 text-sm font-medium text-slate-600 transition-all hover:bg-surface-elevated/80 hover:text-slate-800"
        >
          {t("summary.restart")}
        </button>
      </div>
    </div>
  );
}

function ConfettiRibbonLayer() {
  const ribbons = useMemo(
    () =>
      Array.from({ length: 26 }, (_, i) => {
        const left = ((i * 37) % 100) + (i % 3) * 0.6;
        const delay = (i % 7) * 0.35;
        const duration = 3.8 + (i % 5) * 0.55;
        const sway = 10 + (i % 6) * 2;
        const width = 6 + (i % 4);
        const height = 14 + (i % 5) * 4;
        const colors = ["#f97316", "#facc15", "#22c55e", "#14b8a6", "#38bdf8", "#f43f5e"];
        return {
          id: `ribbon-${i}`,
          left: Math.min(99, left),
          delay,
          duration,
          sway,
          width,
          height,
          color: colors[i % colors.length],
        };
      }),
    [],
  );

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {ribbons.map((ribbon) => (
        <span
          key={ribbon.id}
          className="summary-ribbon"
          style={{
            left: `${ribbon.left}%`,
            width: `${ribbon.width}px`,
            height: `${ribbon.height}px`,
            backgroundColor: ribbon.color,
            animationDelay: `${ribbon.delay}s`,
            animationDuration: `${ribbon.duration}s`,
            ["--ribbon-sway" as string]: `${ribbon.sway}px`,
          }}
        />
      ))}
    </div>
  );
}

function StatCard({
  label,
  value,
  suffix,
  color,
}: {
  label: string;
  value: string;
  suffix: string;
  color: string;
}) {
  return (
    <div className="rounded-xl bg-surface-elevated/50 p-4 text-center">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`mt-1 font-mono text-xl font-bold ${color}`}>
        {value}
        <span className="ml-0.5 text-xs font-normal text-slate-400">
          {suffix}
        </span>
      </p>
    </div>
  );
}
