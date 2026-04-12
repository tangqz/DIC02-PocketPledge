import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { API_BASE, useAuthStore } from "@/stores/authStore";
import { useSessionStore } from "@/stores/sessionStore";

interface AssessmentItem {
  id: string;
  assessment_type: string;
  score: number;
  severity: string;
  positive_screen: boolean;
  created_at?: string | null;
}

interface AssessmentListResponse {
  ok: boolean;
  user_id: number;
  items: AssessmentItem[];
}

function severityLabel(severity: string, locale: "zh" | "en"): string {
  const normalized = severity.trim().toLowerCase();
  if (locale === "en") {
    if (normalized === "moderate_or_above") {
      return "moderate+";
    }
    return normalized || "unknown";
  }

  if (normalized === "minimal") {
    return "较轻";
  }
  if (normalized === "mild") {
    return "轻度";
  }
  if (normalized === "moderate_or_above") {
    return "中度及以上";
  }
  return "未知";
}

function formatDateLabel(createdAt: string | null | undefined, locale: "zh" | "en"): string {
  if (!createdAt) {
    return locale === "zh" ? "刚刚" : "recently";
  }

  const normalized = /(?:z|[+-]\d{2}:\d{2})$/i.test(createdAt) ? createdAt : `${createdAt}Z`;
  const ts = Date.parse(normalized);
  if (Number.isNaN(ts)) {
    return locale === "zh" ? "最近" : "recent";
  }

  const value = new Date(ts);
  return locale === "zh"
    ? `${value.getMonth() + 1}/${value.getDate()}`
    : `${value.getMonth() + 1}/${value.getDate()}`;
}

export default function AssessmentInsightsPanel() {
  const { locale, t } = useI18n();
  const wellbeingSyncVersion = useSessionStore((s) => s.wellbeingSyncVersion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState<AssessmentItem[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const token = useAuthStore.getState().token;
      const response = await fetch(`${API_BASE}/api/business/me/assessments?days=30&limit=6`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        setError(payload.detail ?? t("common.loadFailed"));
        return;
      }

      const payload = (await response.json()) as AssessmentListResponse;
      setItems(payload.items ?? []);
    } catch {
      setError(t("common.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
  }, [loadData, wellbeingSyncVersion]);

  const latestByType = useMemo(() => {
    const grouped = new Map<string, AssessmentItem>();
    for (const item of items) {
      const key = item.assessment_type.trim().toLowerCase();
      if (!grouped.has(key)) {
        grouped.set(key, item);
      }
    }
    return {
      phq2: grouped.get("phq2") ?? null,
      gad2: grouped.get("gad2") ?? null,
    };
  }, [items]);

  const combined = useMemo(() => {
    const phq2 = latestByType.phq2;
    const gad2 = latestByType.gad2;
    if (!phq2 && !gad2) {
      return null;
    }

    const shouldSeekSupport = Boolean(phq2?.positive_screen || gad2?.positive_screen);
    const riskLevel: "low" | "moderate" | "high" =
      (phq2?.score ?? 0) >= 5 || (gad2?.score ?? 0) >= 5 || Boolean(phq2?.positive_screen && gad2?.positive_screen)
        ? "high"
        : shouldSeekSupport
          ? "moderate"
          : "low";

    return {
      phq2,
      gad2,
      shouldSeekSupport,
      riskLevel,
      latestDate: phq2?.created_at ?? gad2?.created_at ?? null,
    };
  }, [latestByType]);

  return (
    <div className="border-t border-slate-200 px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-600">
          {locale === "zh" ? "最近自测摘要" : "Recent Self-Check"}
        </p>
        <button
          onClick={() => void loadData()}
          className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-200"
        >
          {t("common.refresh")}
        </button>
      </div>

      {loading && <p className="text-xs text-slate-400">{t("common.loading")}</p>}
      {!loading && error && <p className="text-xs text-rose-600">{error}</p>}

      {!loading && !error && !combined && (
        <p className="text-xs text-slate-400">
          {locale === "zh" ? "还没有心理自测记录" : "No self-check records yet"}
        </p>
      )}

      {!loading && !error && combined && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {combined.phq2 && (
              <span className="rounded-full bg-sky-50 px-2.5 py-1 text-[11px] text-sky-700">
                {`PHQ-2 ${combined.phq2.score}/6 · ${severityLabel(combined.phq2.severity, locale)}`}
              </span>
            )}
            {combined.gad2 && (
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] text-emerald-700">
                {`GAD-2 ${combined.gad2.score}/6 · ${severityLabel(combined.gad2.severity, locale)}`}
              </span>
            )}
          </div>

          <p className="text-[11px] text-slate-500">
            {locale === "zh"
              ? `最近一次更新：${formatDateLabel(combined.latestDate, locale)}；当前整体关注等级：${combined.riskLevel === "high" ? "较高" : combined.riskLevel === "moderate" ? "中等" : "较低"}。`
              : `Latest update: ${formatDateLabel(combined.latestDate, locale)}; current concern level: ${combined.riskLevel}.`}
          </p>

          <p className="text-[11px] text-slate-500">
            {locale === "zh"
              ? combined.riskLevel === "high"
                ? "这更像一盏提醒灯，不是诊断。最近如果持续很难受，尽量联系专业支持或可信任的人。"
                : combined.riskLevel === "moderate"
                  ? "你最近值得多照顾一点自己。可以继续和暖伴聊，或把压力最大的那件事单独拆开。"
                  : "整体看还算平稳。继续偶尔做一次小测，会更容易看到自己的变化。"
              : combined.riskLevel === "high"
                ? "Treat this as a signal, not a diagnosis. If things keep feeling heavy, reaching out to a professional or someone you trust would help."
                : combined.riskLevel === "moderate"
                  ? "You may need a bit more care lately. Keep talking with WarmBuddy, or break down the one thing that feels heaviest."
                  : "Things look relatively steady. Checking in once in a while can help you notice change earlier."}
          </p>

          {combined.shouldSeekSupport && (
            <p className="rounded-lg bg-amber-50 px-2.5 py-2 text-[11px] text-amber-800">
              {locale === "zh"
                ? "仅供自我观察，不构成诊断。若持续痛苦或有自伤想法，请尽快联系专业支持；全国 24 小时心理援助热线：400-161-9995。"
                : "For self-observation only, not a diagnosis. If distress persists or you have thoughts of self-harm, seek professional support promptly; CN crisis line: 400-161-9995."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}