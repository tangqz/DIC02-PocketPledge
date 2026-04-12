import { useMemo, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { API_BASE, useAuthStore } from "@/stores/authStore";

type AssessmentType = "phq2" | "gad2";

interface AssessmentModalProps {
  onClose?: () => void;
}

interface AssessmentSubmitResponse {
  ok: boolean;
  id: string;
  assessment_type: string;
  score: number;
  severity: string;
  positive_screen: boolean;
  reward_granted: number;
  balance_after: number;
  created_at: string | null;
}

interface CombinedAssessmentResult {
  phq2: AssessmentSubmitResponse;
  gad2: AssessmentSubmitResponse;
  totalReward: number;
  balanceAfter: number;
  shouldSeekSupport: boolean;
  riskLevel: "low" | "moderate" | "high";
}

const QUESTIONS: Array<{ type: AssessmentType; zh: string; en: string }> = [
  {
    type: "phq2",
    zh: "过去两周，你有多少时间对做事缺乏兴趣或乐趣？",
    en: "Over the last 2 weeks, how often have you had little interest or pleasure in doing things?",
  },
  {
    type: "phq2",
    zh: "过去两周，你有多少时间感到情绪低落、沮丧或绝望？",
    en: "Over the last 2 weeks, how often have you felt down, depressed, or hopeless?",
  },
  {
    type: "gad2",
    zh: "过去两周，你有多少时间感到紧张、焦虑或绷不住？",
    en: "Over the last 2 weeks, how often have you felt nervous, anxious, or on edge?",
  },
  {
    type: "gad2",
    zh: "过去两周，你有多少时间无法停止或控制担忧？",
    en: "Over the last 2 weeks, how often have you not been able to stop or control worrying?",
  },
];

const OPTIONS = [
  { value: 0, zh: "完全没有", en: "Not at all" },
  { value: 1, zh: "几天", en: "Several days" },
  { value: 2, zh: "一半以上天数", en: "More than half the days" },
  { value: 3, zh: "几乎每天", en: "Nearly every day" },
];

export default function AssessmentModal({ onClose }: AssessmentModalProps) {
  const { locale, t } = useI18n();
  const [answers, setAnswers] = useState<[number, number, number, number]>([0, 0, 0, 0]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>("");
  const [result, setResult] = useState<CombinedAssessmentResult | null>(null);

  const phq2Score = useMemo(() => answers[0] + answers[1], [answers]);
  const gad2Score = useMemo(() => answers[2] + answers[3], [answers]);
  const totalScore = phq2Score + gad2Score;

  const setAnswer = (index: 0 | 1 | 2 | 3, value: number) => {
    setAnswers((prev) => {
      const next: [number, number, number, number] = [...prev] as [number, number, number, number];
      next[index] = value;
      return next;
    });
  };

  const submitSingleAssessment = async (
    assessmentType: AssessmentType,
    pairAnswers: [number, number],
  ): Promise<AssessmentSubmitResponse> => {
    const token = useAuthStore.getState().token;
    const response = await fetch(`${API_BASE}/api/business/me/assessments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        assessment_type: assessmentType,
        answers: pairAnswers,
      }),
    });

    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(payload.detail ?? t("common.submitFailed"));
    }

    return (await response.json()) as AssessmentSubmitResponse;
  };

  const submitAssessment = async () => {
    setSubmitting(true);
    setError("");
    setResult(null);
    try {
      const [phq2, gad2] = await Promise.all([
        submitSingleAssessment("phq2", [answers[0], answers[1]]),
        submitSingleAssessment("gad2", [answers[2], answers[3]]),
      ]);

      const shouldSeekSupport = phq2.positive_screen || gad2.positive_screen;
      const riskLevel: CombinedAssessmentResult["riskLevel"] =
        phq2.score >= 5 || gad2.score >= 5 || (phq2.positive_screen && gad2.positive_screen)
          ? "high"
          : shouldSeekSupport
            ? "moderate"
            : "low";

      setResult({
        phq2,
        gad2,
        totalReward: phq2.reward_granted + gad2.reward_granted,
        balanceAfter: Math.max(phq2.balance_after, gad2.balance_after),
        shouldSeekSupport,
        riskLevel,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("common.networkRetry");
      setError(msg || t("common.networkRetry"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-[min(92vw,640px)] max-h-[85vh] overflow-y-auto rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-700">
          {t("assessment.title")}
        </h3>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
          >
            {t("common.close")}
          </button>
        )}
      </div>

      <div className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
        {t("assessment.disclaimer")}
      </div>

      <div className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        {locale === "zh"
          ? "四题联测（PHQ-2 + GAD-2），帮助你快速观察最近两周的情绪与焦虑状态。"
          : "4-item combined screening (PHQ-2 + GAD-2) to quickly check mood and anxiety over the past 2 weeks."}
      </div>

      <div className="space-y-3">
        {QUESTIONS.map((question, index) => (
          <div key={`${question.type}-${index}`} className="rounded-xl border border-slate-200 p-3">
            <p className="mb-2 text-sm text-slate-700">{locale === "zh" ? question.zh : question.en}</p>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              {OPTIONS.map((option) => (
                <button
                  key={`${question.type}-${index}-${option.value}`}
                  onClick={() => setAnswer(index as 0 | 1 | 2 | 3, option.value)}
                  className={`rounded-lg px-2 py-1.5 text-xs ${
                    answers[index] === option.value
                      ? "bg-sky-500 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {locale === "zh" ? option.zh : option.en}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {locale === "zh"
            ? `PHQ-2: ${phq2Score}/6 · GAD-2: ${gad2Score}/6 · 总分: ${totalScore}/12`
            : `PHQ-2: ${phq2Score}/6 · GAD-2: ${gad2Score}/6 · Total: ${totalScore}/12`}
        </p>
        <button
          onClick={submitAssessment}
          disabled={submitting}
          className="rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {submitting ? "..." : t("assessment.submitAndSave")}
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}

      {result && (
        <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          <p>
            {locale === "zh"
              ? `已记录：PHQ-2 ${result.phq2.score}/6（${result.phq2.severity}），GAD-2 ${result.gad2.score}/6（${result.gad2.severity}）`
              : `Saved: PHQ-2 ${result.phq2.score}/6 (${result.phq2.severity}), GAD-2 ${result.gad2.score}/6 (${result.gad2.severity})`}
          </p>
          <p>
            {locale === "zh"
              ? `奖励积分 +${result.totalReward}，当前余额 ${result.balanceAfter}`
              : `Reward +${result.totalReward}, balance ${result.balanceAfter}`}
          </p>
          <p className="mt-1">
            {locale === "zh"
              ? `综合风险等级：${result.riskLevel === "high" ? "较高" : result.riskLevel === "moderate" ? "中等" : "较低"}`
              : `Overall risk level: ${result.riskLevel}`}
          </p>
          {result.shouldSeekSupport && (
            <p className="mt-2 rounded-md bg-amber-100 px-2 py-1 text-amber-800">
              {locale === "zh"
                ? "筛查提示你可能需要更多支持。若持续感到痛苦或有自伤想法，请立即联系心理援助热线 400-161-9995，或拨打当地紧急电话。"
                : "Screening suggests you may need extra support. If distress persists or you have thoughts of self-harm, call a crisis line (CN: 400-161-9995) or your local emergency number immediately."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
