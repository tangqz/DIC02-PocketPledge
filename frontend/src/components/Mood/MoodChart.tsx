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
  startTimestamp: number;
  endTimestamp: number;
}

const DAY_BUCKET_MS = 24 * 60 * 60 * 1000;
const RECENT_BUCKET_MS = 60 * 60 * 1000;
const RECENT_BUCKET_COUNT = 12;

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
  neutral: { zh: "平稳", en: "Neutral" },
};

const EMOTION_DOMINANCE_WEIGHT: Record<string, number> = {
  neutral: 0.5,
  calm: 0.85,
};

function normalizeEmotion(emotion: string): string {
  const normalized = emotion.toLowerCase();
  if (EMOTION_LABELS[normalized]) {
    return normalized;
  }
  if (normalized === "fatigued" || normalized === "sleepy") {
    return "tired";
  }
  if (normalized === "stress") {
    return "stressed";
  }
  if (normalized === "relaxed") {
    return "calm";
  }
  return "neutral";
}

function emotionColor(emotion: string): string {
  return EMOTION_COLORS[normalizeEmotion(emotion)] ?? "bg-slate-300";
}

function emotionLabel(emotion: string, locale: "zh" | "en"): string {
  const normalized = normalizeEmotion(emotion);
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
  const normalized = /(?:z|[+-]\d{2}:\d{2})$/i.test(createdAt) ? createdAt : `${createdAt}Z`;
  const value = Date.parse(normalized);
  return Number.isNaN(value) ? null : value;
}

function formatDayLabel(timestamp: number, locale: "zh" | "en"): string {
  const d = new Date(timestamp);
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return locale === "zh" ? `${m}/${day}` : `${m}/${day}`;
}

function formatHourLabel(timestamp: number): string {
  const d = new Date(timestamp);
  return `${String(d.getHours()).padStart(2, "0")}:00`;
}

function summarizeBucket(events: EmotionEvent[]): Pick<DayMoodSummary, "count" | "dominantEmotion" | "avgIntensity"> {
  if (events.length === 0) {
    return {
      count: 0,
      dominantEmotion: "neutral",
      avgIntensity: 0,
    };
  }

  const scores = new Map<string, number>();
  let intensitySum = 0;
  for (const event of events) {
    const emotion = normalizeEmotion(event.emotion);
    const intensity = Math.max(1, Math.min(event.intensity, 5));
    const weight = EMOTION_DOMINANCE_WEIGHT[emotion] ?? 1;
    intensitySum += intensity;
    scores.set(emotion, (scores.get(emotion) ?? 0) + intensity * weight);
  }

  const neutralScore = scores.get("neutral") ?? 0;
  const nonNeutralEntries = [...scores.entries()].filter(([emotion]) => emotion !== "neutral");
  let dominantEmotion = "neutral";
  let dominantScore = neutralScore;

  for (const [emotion, score] of nonNeutralEntries) {
    if (score > dominantScore || (dominantEmotion === "neutral" && score >= neutralScore * 0.85)) {
      dominantEmotion = emotion;
      dominantScore = score;
    }
  }

  return {
    count: events.length,
    dominantEmotion,
    avgIntensity: Math.round((intensitySum / events.length) * 10) / 10,
  };
}

function buildFixedBuckets(
  events: EmotionEvent[],
  latestBucketStart: number,
  bucketCount: number,
  bucketMs: number,
  labelFormatter: (timestamp: number) => string,
): DayMoodSummary[] {
  const summaries: DayMoodSummary[] = [];

  for (let index = bucketCount - 1; index >= 0; index -= 1) {
    const startTimestamp = latestBucketStart - index * bucketMs;
    const endTimestamp = startTimestamp + bucketMs;
    const items = events.filter(
      (event) => event.timestamp >= startTimestamp && event.timestamp < endTimestamp,
    );
    const summary = summarizeBucket(items);
    const key = `${bucketMs}-${startTimestamp}`;
    summaries.push({
      key,
      label: labelFormatter(startTimestamp),
      startTimestamp,
      endTimestamp,
      ...summary,
    });
  }

  return summaries;
}

function buildDaySummaries(
  events: EmotionEvent[],
  locale: "zh" | "en",
): DayMoodSummary[] {
  const latestDayStart = new Date();
  latestDayStart.setHours(0, 0, 0, 0);
  return buildFixedBuckets(
    events,
    latestDayStart.getTime(),
    7,
    DAY_BUCKET_MS,
    (timestamp) => formatDayLabel(timestamp, locale),
  );
}

function buildRecentTimeSummaries(
  events: EmotionEvent[],
): DayMoodSummary[] {
  const latestHourStart = new Date();
  latestHourStart.setMinutes(0, 0, 0);
  return buildFixedBuckets(
    events,
    latestHourStart.getTime(),
    RECENT_BUCKET_COUNT,
    RECENT_BUCKET_MS,
    formatHourLabel,
  );
}

export default function MoodChart() {
  const { locale, t } = useI18n();
  const emotionHistory = useSessionStore((s) => s.emotionHistory);
  const wellbeingSyncVersion = useSessionStore((s) => s.wellbeingSyncVersion);
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
  }, [loadMoodEntries, wellbeingSyncVersion]);

  const mergedHistory = useMemo(() => {
    const fromBackend: EmotionEvent[] = entries
      .map((item) => {
        const timestamp = toTimestamp(item.created_at);
        if (timestamp === null) {
          return null;
        }
        return {
          emotion: normalizeEmotion(item.emotion),
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

  const daySummaries = useMemo(
    () => buildDaySummaries(mergedHistory, locale),
    [locale, mergedHistory],
  );
  const recentTimeSummaries = useMemo(
    () => buildRecentTimeSummaries(mergedHistory),
    [mergedHistory],
  );
  const maxAvgIntensity = useMemo(
    () => Math.max(...daySummaries.map((item) => item.avgIntensity), 1),
    [daySummaries],
  );
  const recentMaxAvgIntensity = useMemo(
    () => Math.max(...recentTimeSummaries.map((item) => item.avgIntensity), 1),
    [recentTimeSummaries],
  );
  const visibleRecentEmotions = useMemo(
    () => [...new Set(
      recentTimeSummaries
        .filter((item) => item.count > 0)
        .map((item) => normalizeEmotion(item.dominantEmotion)),
    )],
    [recentTimeSummaries],
  );
  const weeklySummary = useMemo(() => {
    if (mergedHistory.length === 0) {
      return "";
    }

    const sevenDaysAgo = Date.now() - 7 * DAY_BUCKET_MS;
    const recentEvents = mergedHistory.filter((item) => item.timestamp >= sevenDaysAgo);
    if (recentEvents.length === 0) {
      return "";
    }

    const summary = summarizeBucket(recentEvents);
    const label = emotionLabel(summary.dominantEmotion, locale);
    return locale === "zh"
      ? `本周主要情绪：${label}，平均强度 ${summary.avgIntensity}/5`
      : `Main mood this week: ${label}, avg ${summary.avgIntensity}/5`;
  }, [locale, mergedHistory]);

  if (!loading && !error && mergedHistory.length === 0) {
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

      {weeklySummary && (
        <p className="mb-2 text-[11px] text-slate-500">{weeklySummary}</p>
      )}

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
                    title={`${item.label} · ${emotionLabel(item.dominantEmotion, locale)} · ${item.avgIntensity}/5 · ${item.count}`}
                  />
                </div>
                <span className="text-[10px] text-slate-400">{item.label}</span>
              </div>
            );
          })}
        </div>
      )}

      {!error && (
        <>
          <p className="mb-2 text-[11px] font-medium text-slate-500">
            {locale === "zh" ? "最近 12 小时情绪时间轴" : "Last 12 Hours"}
          </p>
          <p className="mb-2 text-[10px] text-slate-400">
            {locale === "zh" ? "按 1 小时聚合，显示窗口平均强度" : "Grouped by hour, showing average intensity per window"}
          </p>

          {recentTimeSummaries.some((item) => item.count > 0) ? (
            <>
              <div className="overflow-x-auto pb-1">
                <div className="grid min-w-[24rem] grid-cols-12 gap-1.5">
                  {recentTimeSummaries.map((item) => {
                    const barHeight =
                      item.count === 0
                        ? 4
                        : Math.max(8, Math.round((item.avgIntensity / recentMaxAvgIntensity) * 46));

                    return (
                      <div key={item.key} className="flex flex-col items-center gap-1">
                        <div className="flex h-14 items-end">
                          <div
                            className={`w-3 rounded-t ${emotionColor(item.dominantEmotion)}`}
                            style={{ height: `${barHeight}px` }}
                            title={`${item.label} · ${emotionLabel(item.dominantEmotion, locale)} · ${item.avgIntensity}/5 · ${item.count}`}
                          />
                        </div>
                        <span className="text-[10px] text-slate-400">{item.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="mt-2 flex flex-wrap gap-2">
                {visibleRecentEmotions.map((emotion) => (
                  <span key={emotion} className="flex items-center gap-1 text-[10px] text-slate-500">
                    <span className={`inline-block h-2 w-2 rounded-full ${emotionColor(emotion)}`} />
                    {emotionLabel(emotion, locale)}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-slate-400">
              {locale === "zh" ? "最近 12 小时暂无新增情绪记录" : "No emotion data in the last 12 hours"}
            </p>
          )}
        </>
      )}
    </div>
  );
}
