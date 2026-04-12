import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { API_BASE, useAuthStore } from "@/stores/authStore";
import { useSessionStore } from "@/stores/sessionStore";

interface CorrelationBucket {
  label: string;
  count: number;
  avg_intensity: number;
}

interface MealCorrelationResponse {
  ok: boolean;
  user_id: number;
  days: number;
  total_records: number;
  buckets: CorrelationBucket[];
}

const FALLBACK_RESPONSE: MealCorrelationResponse = {
  ok: true,
  user_id: 0,
  days: 30,
  total_records: 0,
  buckets: [],
};

const EMOTION_LABELS: Record<string, { zh: string; en: string }> = {
  happy: { zh: "开心", en: "happy" },
  calm: { zh: "平静", en: "calm" },
  anxious: { zh: "焦虑", en: "anxious" },
  stressed: { zh: "压力大", en: "stressed" },
  tired: { zh: "疲惫", en: "tired" },
  neutral: { zh: "一般", en: "neutral" },
  sad: { zh: "难过", en: "sad" },
  angry: { zh: "生气", en: "angry" },
  unspecified: { zh: "未注明", en: "unspecified" },
};

function emotionLabel(label: string, locale: "zh" | "en"): string {
  const normalized = label.trim().toLowerCase();
  const labels = EMOTION_LABELS[normalized];
  if (!labels) {
    return normalized;
  }
  return locale === "zh" ? labels.zh : labels.en;
}

export default function MealCorrelationPanel() {
  const { locale, t } = useI18n();
  const wellbeingSyncVersion = useSessionStore((s) => s.wellbeingSyncVersion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [response, setResponse] = useState<MealCorrelationResponse>(FALLBACK_RESPONSE);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const token = useAuthStore.getState().token;
      const result = await fetch(`${API_BASE}/api/business/me/meal-correlation?days=30`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!result.ok) {
        const payload = (await result.json().catch(() => ({}))) as { detail?: string };
        setError(payload.detail ?? t("common.loadFailed"));
        return;
      }
      const payload = (await result.json()) as MealCorrelationResponse;
      setResponse(payload);
    } catch {
      setError(t("common.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
  }, [loadData, wellbeingSyncVersion]);

  const maxCount = useMemo(() => {
    if (response.buckets.length === 0) {
      return 1;
    }
    return Math.max(...response.buckets.map((item) => item.count), 1);
  }, [response.buckets]);
  const leadingBucket = useMemo(() => response.buckets[0] ?? null, [response.buckets]);

  return (
    <div className="border-t border-slate-200 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-600">
          {t("meal.correlation")}
        </p>
        <button
          onClick={() => void loadData()}
          className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-200"
        >
          {t("common.refresh")}
        </button>
      </div>

      {loading && (
        <p className="text-xs text-slate-400">
          {t("common.loading")}
        </p>
      )}

      {!loading && error && <p className="text-xs text-rose-600">{error}</p>}

      {!loading && !error && response.total_records === 0 && (
        <p className="text-xs text-slate-400">
          {t("meal.noRecords")}
        </p>
      )}

      {!loading && !error && response.total_records > 0 && (
        <div className="space-y-2">
          {leadingBucket && (
            <p className="text-[11px] text-slate-500">
              {locale === "zh"
                ? `最近 ${response.days} 天里，“${emotionLabel(leadingBucket.label, locale)}”相关记录最多，平均强度 ${leadingBucket.avg_intensity}/5。`
                : `In the last ${response.days} days, ${emotionLabel(leadingBucket.label, locale)} appears most often, with an average intensity of ${leadingBucket.avg_intensity}/5.`}
            </p>
          )}

          {response.buckets.map((bucket) => {
            const width = `${Math.round((bucket.count / maxCount) * 100)}%`;
            return (
              <div key={bucket.label}>
                <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
                  <span>{emotionLabel(bucket.label, locale)}</span>
                  <span>
                    {locale === "zh"
                      ? `${bucket.count} 次, 平均强度 ${bucket.avg_intensity}`
                      : `${bucket.count} logs, avg ${bucket.avg_intensity}`}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-sky-400"
                    style={{ width }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
