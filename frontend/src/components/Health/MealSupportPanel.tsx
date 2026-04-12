import { useCallback, useEffect, useMemo, useState } from "react";

import {
  buildMealSupportCompletedReflection,
  buildMealSupportStartedReflection,
  sendCompanionWellbeingReflection,
  syncWellbeingAfterSave,
} from "@/lib/wellbeing";
import { useI18n } from "@/lib/i18n";
import { useSend } from "@/lib/sendContext";
import { API_BASE, useAuthStore } from "@/stores/authStore";
import type { EmotionEvent } from "@/stores/sessionStore";

export type MealSupportPhase = "pre" | "during" | "post";

export interface MealSupportMealContext {
  mealInfo: string;
  mealEmotion: string;
  intensity: number;
  context: string;
  timestamp: number;
}

interface MealJournalItem {
  id: string;
  meal_info: string;
  meal_emotion: string;
  emotion: string;
  intensity: number;
  context: string;
}

interface MealJournalListResponse {
  ok: boolean;
  user_id: number;
  items: MealJournalItem[];
}

interface MealSupportResultState {
  title: string;
  summary: string;
  trendInsight: string;
  reward: number;
}

interface MealSupportPanelProps {
  initialPhase: MealSupportPhase;
  latestMeal: MealSupportMealContext | null;
  currentEmotion: EmotionEvent | null;
  onClose: () => void;
}

type SupportNeed = "stay-close" | "less-talking" | "ground-me";
type RescueFocus = "compensate" | "shame" | "hide" | "panic";

const FEELING_OPTIONS = [
  { value: "anxious", zh: "焦虑", en: "Anxious" },
  { value: "sad", zh: "内疚 / 难受", en: "Guilty / upset" },
  { value: "tired", zh: "麻木", en: "Numb" },
  { value: "stressed", zh: "害怕 / 很绷", en: "Scared / tense" },
] as const;

const SUPPORT_NEEDS = [
  { value: "stay-close", zh: "陪我待着", en: "Stay with me" },
  { value: "less-talking", zh: "少说一点", en: "Keep it minimal" },
  { value: "ground-me", zh: "提醒我先稳住", en: "Help me ground" },
] as const;

const RESCUE_FOCUSES = [
  { value: "compensate", zh: "补偿冲动", en: "Urge to compensate" },
  { value: "shame", zh: "羞耻和内疚", en: "Shame and guilt" },
  { value: "hide", zh: "很想躲开", en: "Want to hide" },
  { value: "panic", zh: "胃里发慌", en: "Panic in my body" },
] as const;

function clampIntensity(value: number): number {
  return Math.max(1, Math.min(value, 5));
}

function normalizeSupportEmotion(raw: string | undefined): (typeof FEELING_OPTIONS)[number]["value"] {
  const normalized = String(raw || "").trim().toLowerCase();
  if (normalized === "sad" || normalized === "anxious" || normalized === "tired" || normalized === "stressed") {
    return normalized;
  }
  if (normalized === "angry") {
    return "stressed";
  }
  if (normalized === "calm" || normalized === "happy" || normalized === "neutral") {
    return "anxious";
  }
  return "anxious";
}

function formatPhaseLabel(phase: MealSupportPhase, locale: "zh" | "en"): string {
  if (locale === "en") {
    if (phase === "pre") return "Before meal";
    if (phase === "during") return "During meal";
    return "After meal";
  }
  if (phase === "pre") return "饭前 check-in";
  if (phase === "during") return "饭中陪伴";
  return "饭后救援";
}

function supportNeedLabel(value: SupportNeed, locale: "zh" | "en"): string {
  const option = SUPPORT_NEEDS.find((item) => item.value === value);
  if (!option) {
    return value;
  }
  return locale === "zh" ? option.zh : option.en;
}

function feelingLabel(value: string, locale: "zh" | "en"): string {
  const option = FEELING_OPTIONS.find((item) => item.value === value);
  if (!option) {
    return value;
  }
  return locale === "zh" ? option.zh : option.en;
}

function rescueFocusLabel(value: RescueFocus, locale: "zh" | "en"): string {
  const option = RESCUE_FOCUSES.find((item) => item.value === value);
  if (!option) {
    return value;
  }
  return locale === "zh" ? option.zh : option.en;
}

function phaseIntro(phase: MealSupportPhase, locale: "zh" | "en"): string {
  if (locale === "en") {
    if (phase === "pre") return "A 30-second check-in before the meal.";
    if (phase === "during") return "Short, non-judgmental company while you eat.";
    return "The post-meal ten-minute rescue window.";
  }
  if (phase === "pre") return "先用 30 秒确认你现在最需要什么。";
  if (phase === "during") return "饭中只陪着你，不评价食物，不催你解释。";
  return "饭后这十分钟先不急着做任何决定。";
}

function buildMicroAction(
  locale: "zh" | "en",
  phase: MealSupportPhase,
  supportNeed: SupportNeed,
  rescueFocus: RescueFocus,
): string {
  if (supportNeed === "less-talking") {
    return locale === "zh"
      ? "先别判断这一餐，只把双脚踩稳，坐着就好。"
      : "No analysis for a moment. Just keep both feet on the floor and stay seated.";
  }
  if (supportNeed === "ground-me") {
    return locale === "zh"
      ? "看向一个固定点，慢慢呼气四次，让肩膀掉下来。"
      : "Pick one fixed point, exhale slowly four times, and let your shoulders drop.";
  }
  if (phase === "post" || rescueFocus === "compensate") {
    return locale === "zh"
      ? "这十分钟先不做补偿决定，只陪自己把这一波熬过去。"
      : "For these ten minutes, make no compensation decisions. Just stay with yourself through this wave.";
  }
  return locale === "zh"
    ? "把这一分钟拆小一点，先只陪自己过完这一口。"
    : "Make this minute smaller. Just stay with yourself through the next bite.";
}

function patternBucket(text: string): string {
  const normalized = text.toLowerCase();
  if (/(赶|赶时间|匆忙|rush|rushed|busy)/.test(normalized)) {
    return "rushed";
  }
  if (/(一个人|独自|自己吃|alone|by myself)/.test(normalized)) {
    return "alone";
  }
  if (/(朋友|室友|家人|一起|同学|with|together|friends|family|roommate)/.test(normalized)) {
    return "with-others";
  }
  if (/(晚饭|晚上|dinner|night)/.test(normalized)) {
    return "evening";
  }
  return "general";
}

function buildTrendInsight(items: MealJournalItem[], locale: "zh" | "en"): string {
  if (items.length === 0) {
    return locale === "zh"
      ? "继续多记几次餐时感受，之后会更容易看见自己的模式。"
      : "A few more meal-time check-ins will make your pattern easier to see.";
  }

  const scores = new Map<string, { count: number; intensity: number }>();
  for (const item of items) {
    const combined = `${item.meal_info || ""} ${item.context || ""}`;
    const bucket = patternBucket(combined);
    const previous = scores.get(bucket) ?? { count: 0, intensity: 0 };
    scores.set(bucket, {
      count: previous.count + 1,
      intensity: previous.intensity + clampIntensity(item.intensity),
    });
  }

  const [bucket] = [...scores.entries()].sort((left, right) => {
    const leftScore = left[1].count * 10 + left[1].intensity;
    const rightScore = right[1].count * 10 + right[1].intensity;
    return rightScore - leftScore;
  })[0] ?? ["general", { count: 0, intensity: 0 }];

  if (locale === "en") {
    if (bucket === "rushed") {
      return "Your recent logs suggest rushed meals are more likely to bring tension.";
    }
    if (bucket === "alone") {
      return "Your recent logs suggest eating alone is a moment that may need extra care.";
    }
    if (bucket === "with-others") {
      return "Your recent logs suggest shared meals can still carry pressure, so it helps to check in early.";
    }
    if (bucket === "evening") {
      return "Your recent logs suggest evenings are a more sensitive meal window for you.";
    }
    return "Your recent meal logs show this is worth noticing earlier, not only after it gets heavy.";
  }

  if (bucket === "rushed") {
    return "最近记录看起来，赶着吃的时候你更容易整个人绷起来。";
  }
  if (bucket === "alone") {
    return "最近记录看起来，一个人吃饭像是更需要被接住的时刻。";
  }
  if (bucket === "with-others") {
    return "最近记录看起来，和别人一起吃时也值得更早照看自己的压力。";
  }
  if (bucket === "evening") {
    return "最近记录看起来，晚饭前后更像是你需要多一点陪伴的窗口。";
  }
  return "最近餐时记录提示你，越早在饭点前后停下来照看自己，越容易稳住。";
}

export default function MealSupportPanel({
  initialPhase,
  latestMeal,
  currentEmotion,
  onClose,
}: MealSupportPanelProps) {
  const { locale } = useI18n();
  const send = useSend();
  const derivedEmotion = normalizeSupportEmotion(currentEmotion?.emotion || latestMeal?.mealEmotion);
  const derivedIntensity = clampIntensity(currentEmotion?.intensity ?? latestMeal?.intensity ?? (initialPhase === "post" ? 4 : 3));

  const [phase, setPhase] = useState<MealSupportPhase>(initialPhase);
  const [selectedFeeling, setSelectedFeeling] = useState<(typeof FEELING_OPTIONS)[number]["value"]>(derivedEmotion);
  const [supportNeed, setSupportNeed] = useState<SupportNeed>(initialPhase === "post" ? "ground-me" : "stay-close");
  const [startIntensity, setStartIntensity] = useState(derivedIntensity);
  const [endIntensity, setEndIntensity] = useState(Math.max(1, derivedIntensity - 1));
  const [rescueFocus, setRescueFocus] = useState<RescueFocus>("compensate");
  const [notes, setNotes] = useState(latestMeal?.context ?? "");
  const [phaseStartedAt, setPhaseStartedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [result, setResult] = useState<MealSupportResultState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (phase !== "post" || result) {
      return undefined;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [phase, result]);

  const remainingSeconds = useMemo(() => {
    if (phase !== "post") {
      return 10 * 60;
    }
    return Math.max(0, 10 * 60 - Math.floor((now - phaseStartedAt) / 1000));
  }, [now, phase, phaseStartedAt]);

  const microAction = useMemo(
    () => buildMicroAction(locale, phase, supportNeed, rescueFocus),
    [locale, phase, rescueFocus, supportNeed],
  );
  const mealContextLine = latestMeal?.mealInfo
    ? locale === "zh"
      ? `这次相关餐食：${latestMeal.mealInfo}`
      : `Current meal context: ${latestMeal.mealInfo}`
    : locale === "zh"
      ? "可以不写吃了什么，先照顾当下也可以。"
      : "You do not need to explain the food first. Caring for the moment is enough.";

  const triggerSupportReply = useCallback(
    (targetPhase: MealSupportPhase) => {
      sendCompanionWellbeingReflection(
        send,
        buildMealSupportStartedReflection({
          phase: targetPhase,
          emotion: feelingLabel(selectedFeeling, locale),
          intensity: targetPhase === "post" ? endIntensity : startIntensity,
          supportNeed: supportNeedLabel(supportNeed, locale),
          mealInfo: latestMeal?.mealInfo,
          rescueFocus: targetPhase === "post" ? rescueFocusLabel(rescueFocus, locale) : undefined,
        }),
      );
    },
    [endIntensity, latestMeal?.mealInfo, locale, rescueFocus, selectedFeeling, send, startIntensity, supportNeed],
  );

  const moveToPost = useCallback(() => {
    setPhase("post");
    setPhaseStartedAt(Date.now());
    triggerSupportReply("post");
  }, [triggerSupportReply]);

  const fetchTrendInsight = useCallback(async (): Promise<string> => {
    try {
      const token = useAuthStore.getState().token;
      const response = await fetch(`${API_BASE}/api/business/me/meal-journal?days=30&limit=60`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!response.ok) {
        return buildTrendInsight([], locale);
      }
      const payload = (await response.json()) as MealJournalListResponse;
      return buildTrendInsight(payload.items ?? [], locale);
    } catch {
      return buildTrendInsight([], locale);
    }
  }, [locale]);

  const finishSupport = useCallback(async () => {
    setSubmitting(true);
    setError("");
    try {
      const token = useAuthStore.getState().token;
      const response = await fetch(`${API_BASE}/api/business/me/mood`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          emotion: selectedFeeling,
          intensity: endIntensity,
          context:
            locale === "zh"
              ? `meal_support:${formatPhaseLabel(phase, locale)}；起始强度 ${startIntensity}/5；结束强度 ${endIntensity}/5；需要 ${supportNeedLabel(supportNeed, locale)}；最难的是 ${rescueFocusLabel(rescueFocus, locale)}；${notes}`
              : `meal_support:${formatPhaseLabel(phase, locale)}; start ${startIntensity}/5; end ${endIntensity}/5; need ${supportNeedLabel(supportNeed, locale)}; hardest part ${rescueFocusLabel(rescueFocus, locale)}; ${notes}`,
          source: "meal_support",
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        setError(payload.detail ?? (locale === "zh" ? "保存护航结果失败，请稍后再试。" : "Failed to save support result."));
        return;
      }

      const payload = (await response.json()) as { total_reward?: number };
      const reward = Number(payload.total_reward ?? 0);
      const trendInsight = await fetchTrendInsight();

      await syncWellbeingAfterSave({
        emotion: {
          emotion: selectedFeeling,
          intensity: endIntensity,
          cues: rescueFocusLabel(rescueFocus, locale),
          suggestion: "",
        },
      });

      sendCompanionWellbeingReflection(
        send,
        buildMealSupportCompletedReflection({
          phase,
          emotion: feelingLabel(selectedFeeling, locale),
          startIntensity,
          endIntensity,
          supportNeed: supportNeedLabel(supportNeed, locale),
          rescueFocus: rescueFocusLabel(rescueFocus, locale),
          microAction,
          trendInsight,
          totalReward: reward,
        }),
      );

      const delta = startIntensity - endIntensity;
      const title = delta > 0
        ? locale === "zh"
          ? `你把这一波从 ${startIntensity}/5 扛到了 ${endIntensity}/5` 
          : `You carried this wave from ${startIntensity}/5 to ${endIntensity}/5`
        : locale === "zh"
          ? "这一波还没完全散，但你已经没有独自扛着了"
          : "The wave is not gone yet, but you are not carrying it alone now";
      const summary = delta > 0
        ? locale === "zh"
          ? `你没有急着做决定，而是先让自己稳了一下。${microAction}`
          : `You did not rush into a decision. You stabilized first. ${microAction}`
        : locale === "zh"
          ? `最难的时候你还是停下来了。${microAction}`
          : `You still paused at the hardest point. ${microAction}`;

      setResult({
        title,
        summary,
        trendInsight,
        reward,
      });
    } catch {
      setError(locale === "zh" ? "网络异常，请稍后再试。" : "Network error, please retry.");
    } finally {
      setSubmitting(false);
    }
  }, [endIntensity, fetchTrendInsight, locale, microAction, notes, phase, rescueFocus, selectedFeeling, send, startIntensity, supportNeed]);

  return (
    <div className="w-[min(92vw,720px)] overflow-hidden rounded-[28px] border border-orange-100 bg-white/95 shadow-2xl backdrop-blur-sm">
      <div className="bg-[linear-gradient(135deg,#fff4e8_0%,#ffe8dc_48%,#fffaf3_100%)] px-5 pb-4 pt-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-orange-500">
              {locale === "zh" ? "Meal Support" : "Meal Support"}
            </p>
            <h3 className="mt-2 text-2xl font-semibold text-slate-800">
              {locale === "zh" ? "餐时护航" : "Meal-time Escort"}
            </h3>
            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
              {locale === "zh"
                ? "陪你度过最难的饭前和饭后十分钟。这里只做陪伴，不评价食物，不讨论热量、体重或补偿。"
                : "A steady companion for the hardest ten minutes before and after a meal. This space is for care only, not calories, weight, or compensation."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full bg-white/80 px-3 py-1.5 text-xs font-medium text-slate-500 ring-1 ring-orange-100 transition hover:bg-white"
          >
            {locale === "zh" ? "关闭" : "Close"}
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {(["pre", "during", "post"] as MealSupportPhase[]).map((item) => {
            const active = item === phase;
            return (
              <span
                key={item}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  active
                    ? "bg-orange-500 text-white"
                    : "bg-white/75 text-slate-500 ring-1 ring-orange-100"
                }`}
              >
                {formatPhaseLabel(item, locale)}
              </span>
            );
          })}
        </div>
      </div>

      <div className="space-y-5 px-5 py-5">
        {result ? (
          <div className="space-y-4">
            <div className="rounded-[24px] border border-emerald-100 bg-[linear-gradient(135deg,#f5fff8_0%,#fdf6eb_100%)] p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-600">
                {locale === "zh" ? "撑过来了卡片" : "You made it card"}
              </p>
              <h4 className="mt-2 text-xl font-semibold text-slate-800">{result.title}</h4>
              <p className="mt-3 text-sm leading-6 text-slate-600">{result.summary}</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl bg-white/80 p-3 ring-1 ring-emerald-100">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-600">
                    {locale === "zh" ? "这次撑住了什么" : "What you held through"}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">
                    {locale === "zh"
                      ? `${rescueFocusLabel(rescueFocus, locale)}是这次最强的一波，但你没有马上跟着它走。`
                      : `${rescueFocusLabel(rescueFocus, locale)} was the strongest wave this time, and you did not immediately follow it.`}
                  </p>
                </div>
                <div className="rounded-2xl bg-white/80 p-3 ring-1 ring-orange-100">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-orange-500">
                    {locale === "zh" ? "最近的一个提醒" : "A recent pattern"}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">{result.trendInsight}</p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
                  {locale === "zh" ? `${formatPhaseLabel(phase, locale)} 完成` : `${formatPhaseLabel(phase, locale)} done`}
                </span>
                {result.reward > 0 && (
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
                    {locale === "zh" ? `积分 +${result.reward}` : `Points +${result.reward}`}
                  </span>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-200"
              >
                {locale === "zh" ? "回到暖伴" : "Back to WarmBuddy"}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-700">{formatPhaseLabel(phase, locale)}</p>
                  <p className="mt-1 text-sm text-slate-500">{phaseIntro(phase, locale)}</p>
                </div>
                {phase === "post" && (
                  <div className="rounded-2xl bg-white px-3 py-2 text-center ring-1 ring-orange-100">
                    <p className="text-[11px] uppercase tracking-[0.16em] text-orange-500">
                      {locale === "zh" ? "十分钟窗口" : "Ten-minute window"}
                    </p>
                    <p className="mt-1 text-lg font-semibold text-slate-800">
                      {`${String(Math.floor(remainingSeconds / 60)).padStart(2, "0")}:${String(remainingSeconds % 60).padStart(2, "0")}`}
                    </p>
                  </div>
                )}
              </div>
              <p className="mt-3 text-sm text-slate-600">{mealContextLine}</p>
            </div>

            {phase === "pre" && (
              <div className="grid gap-4 md:grid-cols-[1.2fr,0.8fr]">
                <div className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    {locale === "zh" ? "饭前 30 秒 check-in" : "30-second pre-meal check-in"}
                  </p>
                  <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    {FEELING_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setSelectedFeeling(option.value)}
                        className={`rounded-2xl px-3 py-3 text-left text-sm transition ${
                          selectedFeeling === option.value
                            ? "bg-orange-500 text-white"
                            : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                        }`}
                      >
                        {locale === "zh" ? option.zh : option.en}
                      </button>
                    ))}
                  </div>

                  <div className="mt-4">
                    <label className="text-xs font-medium text-slate-500">
                      {locale === "zh" ? `现在强度 ${startIntensity}/5` : `Current intensity ${startIntensity}/5`}
                    </label>
                    <input
                      type="range"
                      min={1}
                      max={5}
                      value={startIntensity}
                      onChange={(event) => {
                        const next = clampIntensity(Number(event.target.value));
                        setStartIntensity(next);
                        setEndIntensity(Math.max(1, next - 1));
                      }}
                      className="mt-2 w-full accent-orange-500"
                    />
                  </div>

                  <div className="mt-4">
                    <p className="text-xs font-medium text-slate-500">
                      {locale === "zh" ? "这十分钟你更想我怎么陪？" : "How should I stay with you for these minutes?"}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {SUPPORT_NEEDS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => setSupportNeed(option.value)}
                          className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                            supportNeed === option.value
                              ? "bg-slate-900 text-white"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                          }`}
                        >
                          {locale === "zh" ? option.zh : option.en}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mt-4">
                    <textarea
                      value={notes}
                      onChange={(event) => setNotes(event.target.value)}
                      rows={3}
                      placeholder={locale === "zh" ? "这顿饭让你最卡住的地方（可选）" : "What feels hardest about this meal? (optional)"}
                      className="w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-orange-300 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="rounded-2xl border border-orange-100 bg-orange-50/70 p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    {locale === "zh" ? "这一轮你最需要的支持" : "What support looks like now"}
                  </p>
                  <p className="mt-3 text-sm text-slate-600">
                    {locale === "zh"
                      ? `现在更像 ${feelingLabel(selectedFeeling, locale)} ${startIntensity}/5，我会按“${supportNeedLabel(supportNeed, locale)}”的方式陪你。`
                      : `Right now this feels closer to ${feelingLabel(selectedFeeling, locale)} ${startIntensity}/5, and I will stay in a ${supportNeedLabel(supportNeed, locale)} way.`}
                  </p>
                  <p className="mt-4 rounded-2xl bg-white/80 px-3 py-3 text-sm text-slate-600 ring-1 ring-orange-100">
                    {microAction}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      triggerSupportReply("pre");
                      setPhase("during");
                      setPhaseStartedAt(Date.now());
                    }}
                    className="mt-4 w-full rounded-2xl bg-orange-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-orange-600"
                  >
                    {locale === "zh" ? "开始陪我这顿饭" : "Stay with me through this meal"}
                  </button>
                </div>
              </div>
            )}

            {phase === "during" && (
              <div className="grid gap-4 md:grid-cols-[1.15fr,0.85fr]">
                <div className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    {locale === "zh" ? "饭中陪伴" : "During-meal support"}
                  </p>
                  <div className="mt-4 space-y-3">
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {locale === "zh" ? "这一分钟先做这个" : "For this minute"}
                      </p>
                      <p className="mt-2 text-sm text-slate-600">{microAction}</p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {locale === "zh" ? "陪伴方式" : "Companion style"}
                      </p>
                      <p className="mt-2 text-sm text-slate-600">{supportNeedLabel(supportNeed, locale)}</p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {locale === "zh" ? "现在的状态" : "Current state"}
                      </p>
                      <p className="mt-2 text-sm text-slate-600">
                        {`${feelingLabel(selectedFeeling, locale)} ${startIntensity}/5`}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    {locale === "zh" ? "一句够短的提醒" : "A short grounding reminder"}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    {locale === "zh"
                      ? "先不用想对错，也不用把整顿饭想完。先把这一分钟过完，就已经很好。"
                      : "No need to decide if the meal was right or wrong. You do not have to finish the whole emotional story now. Just get through this minute."}
                  </p>
                  <div className="mt-4 grid gap-2">
                    <button
                      type="button"
                      onClick={() => triggerSupportReply("during")}
                      className="rounded-2xl bg-white px-4 py-3 text-sm font-medium text-slate-700 ring-1 ring-amber-100 transition hover:bg-amber-50"
                    >
                      {locale === "zh" ? "让暖伴再陪我一句" : "Ask WarmBuddy for one more line"}
                    </button>
                    <button
                      type="button"
                      onClick={moveToPost}
                      className="rounded-2xl bg-orange-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-orange-600"
                    >
                      {locale === "zh" ? "我吃完了，进入饭后救援" : "I finished eating, go to post-meal rescue"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {phase === "post" && (
              <div className="grid gap-4 md:grid-cols-[1.1fr,0.9fr]">
                <div className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    {locale === "zh" ? "饭后十分钟救援" : "Post-meal ten-minute rescue"}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {RESCUE_FOCUSES.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setRescueFocus(option.value)}
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                          rescueFocus === option.value
                            ? "bg-slate-900 text-white"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        }`}
                      >
                        {locale === "zh" ? option.zh : option.en}
                      </button>
                    ))}
                  </div>

                  <div className="mt-4">
                    <label className="text-xs font-medium text-slate-500">
                      {locale === "zh" ? `现在这股感觉有多强 ${endIntensity}/5` : `How strong is it right now? ${endIntensity}/5`}
                    </label>
                    <input
                      type="range"
                      min={1}
                      max={5}
                      value={endIntensity}
                      onChange={(event) => setEndIntensity(clampIntensity(Number(event.target.value)))}
                      className="mt-2 w-full accent-orange-500"
                    />
                  </div>

                  <div className="mt-4">
                    <textarea
                      value={notes}
                      onChange={(event) => setNotes(event.target.value)}
                      rows={3}
                      placeholder={locale === "zh" ? "现在最想对自己说的话，或最难的一瞬间（可选）" : "What feels hardest right now, or what you wish you could tell yourself (optional)"}
                      className="w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:border-orange-300 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="rounded-2xl border border-orange-100 bg-[linear-gradient(180deg,#fffaf5_0%,#fff3e8_100%)] p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    {locale === "zh" ? "现在只做一件小事" : "One tiny action right now"}
                  </p>
                  <p className="mt-3 rounded-2xl bg-white/85 px-4 py-4 text-sm leading-6 text-slate-600 ring-1 ring-orange-100">
                    {microAction}
                  </p>
                  <p className="mt-4 text-sm text-slate-600">
                    {locale === "zh"
                      ? `你是以 ${startIntensity}/5 进入这一轮的，现在先看能不能把它放低一点，不需要一下子放到零。`
                      : `You entered this rescue at ${startIntensity}/5. The goal is only to lower it a little, not to force it to zero.`}
                  </p>
                  <button
                    type="button"
                    onClick={() => void finishSupport()}
                    disabled={submitting}
                    className="mt-4 w-full rounded-2xl bg-orange-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-orange-600 disabled:opacity-50"
                  >
                    {submitting
                      ? "..."
                      : locale === "zh"
                        ? "完成这次救援"
                        : "Finish this rescue"}
                  </button>
                </div>
              </div>
            )}

            {error && <p className="text-sm text-rose-600">{error}</p>}
          </>
        )}
      </div>
    </div>
  );
}