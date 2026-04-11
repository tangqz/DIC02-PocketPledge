import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { API_BASE, useAuthStore } from "@/stores/authStore";
import { useSessionStore, type EmotionEvent } from "@/stores/sessionStore";

interface MoodEntryItem {
  id: string;
  emotion: string;
  intensity: number;
  source?: string;
  created_at?: string | null;
}

interface MoodEntryListResponse {
  ok: boolean;
  user_id: number;
  items: MoodEntryItem[];
}

interface DayMoodSummary {
  key: string;
  label: string;
  count: number;
  dominantEmotion: string;
  avgIntensity: number;
}

const EMOTION_COLORS: Record<string, string> = {
  happy: "bg-green-400",
  sad: "bg-blue-400",
  anxious: "bg-yellow-400",
  angry: "bg-red-400",
  tired: "bg-purple-400",
  calm: "bg-teal-400",
  loved: "bg-pink-400",
  neutral: "bg-slate-300",
  stressed: "bg-orange-400",
  bored: "bg-gray-400",
};

const EMOTION_LABELS: Record<string, { zh: string; en: string }> = {
  happy: { zh: "开心", en: "Happy" },
  sad: { zh: "难过", en: "Sad" },
  anxious: { zh: "焦虑", en: "Anxious" },
  angry: { zh: "生气", en: "Angry" },
  tired: { zh: "疲惫", en: "Tired" },
  calm: { zh: "平静", en: "Calm" },
  loved: { zh: "被爱", en: "Loved" },
  stressed: { zh: "压力", en: "Stressed" },
  bored: { zh: "无聊", en: "Bored" },
  neutral: { zh: "一般", en: "Neutral" },
};

function emotionColor(emotion: string): string {
  return EMOTION_COLORS[emotion] ?? "bg-slate-300";
}

function emotionLabel(emotion: string, locale: "zh" | "en"): string {
  const normalized = emotion.toLowerCase();
  const labels = EMOTION_LABELS[normalized];
  if (!labels) {
    return normalized;
  }
  return locale === "zh" ? labels.zh : labels.en;
}

function toTimestamp(createdAt: string | null | undefined): number | null {
  if (!createdAt) {
    return null;
  }
  const value = Date.parse(createdAt);
  return Number.isNaN(value) ? null : value;
}

function formatDayLabel(timestamp: number, locale: "zh" | "en"): string {
  const d = new Date(timestamp);
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return locale === "zh" ? `${m}/${day}` : `${m}/${day}`;
}

function buildDaySummaries(
  events: EmotionEvent[],
  locale: "zh" | "en",
): DayMoodSummary[] {
  const end = new Date();
  end.setHours(0, 0, 0, 0);

  const grouped = new Map<string, EmotionEvent[]>();
  for (const event of events) {
    const dt = new Date(event.timestamp);
    if (Number.isNaN(dt.getTime())) {
      continue;
    }
    dt.setHours(0, 0, 0, 0);
    const key = dt.toISOString().slice(0, 10);
    const bucket = grouped.get(key);
    if (bucket) {
      bucket.push(event);
    } else {
      grouped.set(key, [event]);
    }
  }

  const summaries: DayMoodSummary[] = [];
  for (let i = 6; i >= 0; i -= 1) {
    const current = new Date(end);
    current.setDate(end.getDate() - i);
    const key = current.toISOString().slice(0, 10);
    const items = grouped.get(key) ?? [];

    if (items.length === 0) {
      summaries.push({
        key,
        label: formatDayLabel(current.getTime(), locale),
        count: 0,
        dominantEmotion: "neutral",
        avgIntensity: 0,
      });
      continue;
    }

    const freq = new Map<string, number>();
    let totalIntensity = 0;
    for (const event of items) {
      totalIntensity += event.intensity;
      const normalized = event.emotion.toLowerCase();
      freq.set(normalized, (freq.get(normalized) ?? 0) + 1);
    }

    let dominantEmotion = "neutral";
    let dominantCount = -1;
    for (const [emotion, count] of freq.entries()) {
      if (count > dominantCount) {
        dominantEmotion = emotion;
        dominantCount = count;
      }
    }

    summaries.push({
      key,
      label: formatDayLabel(current.getTime(), locale),
      count: items.length,
      dominantEmotion,
      avgIntensity: Math.round((totalIntensity / items.length) * 10) / 10,
    });
  }

  return summaries;
}

export default function MoodChart() {
  const { locale, t } = useI18n();
  const emotionHistory = useSessionStore((s) => s.emotionHistory);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [entries, setEntries] = useState<MoodEntryItem[]>([]);

  const loadMoodEntries = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const token = useAuthStore.getState().token;
      const response = await fetch(`${API_BASE}/api/business/me/mood?days=7&limit=200`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        setError(payload.detail ?? t("common.loadFailed"));
        return;
      }

      const payload = (await response.json()) as MoodEntryListResponse;
      setEntries(payload.items ?? []);
    } catch {
      setError(t("common.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadMoodEntries();
  }, [loadMoodEntries, emotionHistory.length]);

  const mergedHistory = useMemo(() => {
    const fromBackend: EmotionEvent[] = entries
      .map((item) => {
        const timestamp = toTimestamp(item.created_at);
        if (timestamp === null) {
          return null;
        }
        return {
          emotion: item.emotion,
          intensity: item.intensity,
          cues: "",
          suggestion: "",
          timestamp,
        } as EmotionEvent;
      })
      .filter((item): item is EmotionEvent => item !== null);

    if (fromBackend.length === 0) {
      return [...emotionHistory].sort((a, b) => a.timestamp - b.timestamp);
    }

    const latestBackendTs = Math.max(...fromBackend.map((item) => item.timestamp));
    const realtimeTail = emotionHistory.filter((item) => item.timestamp > latestBackendTs);

    return [...fromBackend, ...realtimeTail].sort((a, b) => a.timestamp - b.timestamp);
  }, [emotionHistory, entries]);

  const recent = useMemo(() => mergedHistory.slice(-20), [mergedHistory]);
  const daySummaries = useMemo(
    () => buildDaySummaries(mergedHistory, locale),
    [locale, mergedHistory],
  );
  const maxAvgIntensity = useMemo(
    () => Math.max(...daySummaries.map((item) => item.avgIntensity), 1),
    [daySummaries],
  );

  if (!loading && !error && recent.length === 0) {
    return (
      <div className="px-4 py-3 text-center text-xs text-slate-400">
        {locale === "zh" ? "还没有情绪记录" : "No emotion data yet"}
      </div>
    );
  }

  return (
    <div className="px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-medium text-slate-500">
          {locale === "zh" ? "最近 7 天情绪趋势" : "7-Day Mood Trend"}
        </p>
        <button
          onClick={() => void loadMoodEntries()}
          className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-200"
        >
          {t("common.refresh")}
        </button>
      </div>

      {loading && (
        <p className="mb-2 text-xs text-slate-400">
          {t("common.loading")}
        </p>
      )}

      {!loading && error && <p className="mb-2 text-xs text-rose-600">{error}</p>}

      {!error && daySummaries.length > 0 && (
        <div className="mb-3 grid grid-cols-7 gap-1.5">
          {daySummaries.map((item) => {
            const barHeight =
              item.count === 0
                ? 4
                : Math.max(8, Math.round((item.avgIntensity / maxAvgIntensity) * 46));

            return (
              <div key={item.key} className="flex flex-col items-center gap-1">
                <div className="flex h-14 items-end">
                  <div
                    className={`w-4 rounded-t ${emotionColor(item.dominantEmotion)}`}
                    style={{ height: `${barHeight}px` }}
                    title={`${item.label} · ${emotionLabel(item.dominantEmotion, locale)} · ${item.avgIntensity}/5`}
                  />
                </div>
                <span className="text-[10px] text-slate-400">{item.label}</span>
              </div>
            );
          })}
        </div>
      )}

      {!error && recent.length > 0 && (
        <>
          <p className="mb-2 text-[11px] font-medium text-slate-500">
            {locale === "zh" ? "最近记录" : "Recent Logs"}
          </p>
          <div className="flex items-end gap-1">
            {recent.map((ev: EmotionEvent, i: number) => (
              <div
                key={`${ev.timestamp}-${i}`}
                className="group relative flex flex-col items-center"
              >
                <div
                  className={`w-3 rounded-t ${emotionColor(ev.emotion)}`}
                  style={{ height: `${ev.intensity * 8}px` }}
                  title={`${emotionLabel(ev.emotion, locale)} (${ev.intensity}/5)`}
                />
                <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100">
                  {emotionLabel(ev.emotion, locale)} {ev.intensity}/5
                </div>
              </div>
            ))}
          </div>

          <div className="mt-2 flex flex-wrap gap-2">
            {[...new Set(recent.map((e) => e.emotion.toLowerCase()))].map((emotion) => (
              <span key={emotion} className="flex items-center gap-1 text-[10px] text-slate-500">
                <span className={`inline-block h-2 w-2 rounded-full ${emotionColor(emotion)}`} />
                {emotionLabel(emotion, locale)}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
