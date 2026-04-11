import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { API_BASE, useAuthStore } from "@/stores/authStore";

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

export default function MealCorrelationPanel() {
  const { locale, t } = useI18n();
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
  }, [loadData]);

  const maxCount = useMemo(() => {
    if (response.buckets.length === 0) {
      return 1;
    }
    return Math.max(...response.buckets.map((item) => item.count), 1);
  }, [response.buckets]);

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
          {response.buckets.map((bucket) => {
            const width = `${Math.round((bucket.count / maxCount) * 100)}%`;
            return (
              <div key={bucket.label}>
                <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
                  <span>{bucket.label}</span>
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
