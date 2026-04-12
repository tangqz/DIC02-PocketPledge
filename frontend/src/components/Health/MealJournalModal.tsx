import { useState } from "react";

import { useI18n } from "@/lib/i18n";
import { useSend } from "@/lib/sendContext";
import {
  buildMealRecordedReflection,
  sendCompanionWellbeingReflection,
  syncWellbeingAfterSave,
} from "@/lib/wellbeing";
import { API_BASE, useAuthStore } from "@/stores/authStore";

interface MealJournalModalProps {
  onClose?: () => void;
}

const MEAL_EMOTIONS = [
  { value: "happy", zh: "开心", en: "happy" },
  { value: "calm", zh: "平静", en: "calm" },
  { value: "anxious", zh: "焦虑", en: "anxious" },
  { value: "stressed", zh: "压力大", en: "stressed" },
  { value: "tired", zh: "疲惫", en: "tired" },
  { value: "neutral", zh: "一般", en: "neutral" },
];

export default function MealJournalModal({ onClose }: MealJournalModalProps) {
  const { locale, t } = useI18n();
  const send = useSend();
  const [mealInfo, setMealInfo] = useState("");
  const [mealEmotion, setMealEmotion] = useState("neutral");
  const [intensity, setIntensity] = useState(2);
  const [context, setContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [successText, setSuccessText] = useState("");

  const submitMealJournal = async () => {
    if (!mealInfo.trim()) {
      setError(t("meal.inputRequired"));
      return;
    }

    setSubmitting(true);
    setError("");
    setSuccessText("");
    try {
      const token = useAuthStore.getState().token;
      const response = await fetch(`${API_BASE}/api/business/me/meal-journal`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          meal_info: mealInfo,
          meal_emotion: mealEmotion,
          emotion: mealEmotion,
          intensity,
          context,
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        setError(payload.detail ?? t("common.submitFailed"));
        return;
      }

      const payload = (await response.json()) as {
        total_reward?: number;
        balance_after?: number;
      };
      const reward = Number(payload.total_reward ?? 0);
      const balance = Number(payload.balance_after ?? 0);
      await syncWellbeingAfterSave({
        emotion: {
          emotion: mealEmotion,
          intensity,
          cues: mealInfo.trim(),
          suggestion: "",
        },
      });
      sendCompanionWellbeingReflection(
        send,
        buildMealRecordedReflection({
          mealInfo,
          mealEmotion,
          intensity,
          notes: context,
          totalReward: reward,
        }),
      );
      setSuccessText(
        locale === "zh"
          ? `已记录饮食情绪，奖励 +${reward}，余额 ${balance}，暖伴会结合这次记录继续陪你聊。`
          : `Saved meal mood, reward +${reward}, balance ${balance}. WarmBuddy will respond based on this log.`,
      );
      setMealInfo("");
      setContext("");
    } catch {
      setError(t("common.networkRetry"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-[min(92vw,520px)] rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-700">
          {t("meal.title")}
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

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-xs text-slate-500">
            {t("meal.what")}
          </label>
          <input
            type="text"
            value={mealInfo}
            onChange={(event) => setMealInfo(event.target.value)}
            maxLength={200}
            placeholder={t("meal.whatPlaceholder")}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-sky-400 focus:outline-none"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs text-slate-500">
            {t("meal.afterMood")}
          </label>
          <div className="flex flex-wrap gap-2">
            {MEAL_EMOTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setMealEmotion(option.value)}
                className={`rounded-lg px-2.5 py-1 text-xs ${
                  mealEmotion === option.value
                    ? "bg-sky-500 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {locale === "zh" ? option.zh : option.en}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs text-slate-500">
            {`${t("meal.intensity")}: ${intensity}/5`}
          </label>
          <input
            type="range"
            min={1}
            max={5}
            value={intensity}
            onChange={(event) => setIntensity(Number(event.target.value))}
            className="w-full accent-sky-500"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs text-slate-500">
            {t("meal.notesOptional")}
          </label>
          <textarea
            value={context}
            onChange={(event) => setContext(event.target.value)}
            rows={3}
            maxLength={500}
            placeholder={t("meal.notesPlaceholder")}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-sky-400 focus:outline-none"
          />
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={submitMealJournal}
          disabled={submitting}
          className="rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {submitting ? "..." : t("meal.submit")}
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-100 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-200"
          >
            {t("common.cancel")}
          </button>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
      {successText && <p className="mt-2 text-xs text-emerald-700">{successText}</p>}
    </div>
  );
}
