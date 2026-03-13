import { useEffect, useMemo, useState } from "react";
import type { PlanData, PlanTask } from "@/lib/protocol";
import { useI18n } from "@/lib/i18n";

interface DailyPlanCalendarProps {
  plan: PlanData | null;
  onStartFocusDay?: (payload: { dateKey: string; tasks: CalendarOccurrence[] }) => void;
}

interface CalendarOccurrence {
  dateKey: string;
  taskId: string;
  taskTitle: string;
  completed: boolean;
  estimatedMinutes?: number;
  actualMinutes?: number;
}

interface DaySummary {
  items: CalendarOccurrence[];
  totalMinutes: number;
  completedMinutes: number;
  completedCount: number;
  allDone: boolean;
}

function dateKeyOf(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseDateLike(value: unknown): Date | null {
  if (typeof value !== "string") {
    return null;
  }
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) {
    return null;
  }
  return dt;
}

function addDays(base: Date, days: number): Date {
  const dt = new Date(base);
  dt.setDate(dt.getDate() + days);
  return dt;
}

function monthStart(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function inferWeekdayFromTitle(title: string): number | null {
  const zhMap: Record<string, number> = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "日": 0,
    "天": 0,
  };
  const zhMatch = title.match(/每周\s*([一二三四五六日天])/);
  if (zhMatch && zhMap[zhMatch[1]] !== undefined) {
    return zhMap[zhMatch[1]];
  }

  const enMap: Record<string, number> = {
    mon: 1,
    tue: 2,
    wed: 3,
    thu: 4,
    fri: 5,
    sat: 6,
    sun: 0,
  };
  const enMatch = title.toLowerCase().match(/every\s+(mon|tue|wed|thu|fri|sat|sun)/);
  if (enMatch) {
    return enMap[enMatch[1]];
  }
  return null;
}

function inferRepeatWeeksFromTitle(title: string): number | null {
  const zhMatch = title.match(/持续\s*(\d+)\s*周/);
  if (zhMatch) {
    return Math.max(1, Number(zhMatch[1]));
  }
  const enMatch = title.toLowerCase().match(/(\d+)\s*weeks?/);
  if (enMatch) {
    return Math.max(1, Number(enMatch[1]));
  }
  return null;
}

function buildOccurrences(plan: PlanData | null): CalendarOccurrence[] {
  if (!plan) {
    return [];
  }

  const occurrences: CalendarOccurrence[] = [];
  const today = new Date();

  for (const baseTask of plan.tasks ?? []) {
    const task = baseTask as PlanTask & {
      date?: string;
      dueDate?: string;
      dates?: string[];
      weekdays?: number[];
      repeatCount?: number;
      startDate?: string;
      actualMinutes?: number;
      actualMinutesByDate?: Record<string, number>;
    };

    const actualMinutesByDate =
      task.actualMinutesByDate && typeof task.actualMinutesByDate === "object"
        ? task.actualMinutesByDate
        : {};
    const hasDateSpecificProgress = Object.keys(actualMinutesByDate).length > 0;
    const fallbackTotalActual = Math.max(0, Number(task.actualMinutes || 0));
    const hasSingleExplicitDate =
      Boolean(task.date || task.dueDate) ||
      (Array.isArray(task.dates) && task.dates.length === 1);

    const append = (date: Date) => {
      const dateKey = dateKeyOf(date);
      const dateActual = Math.max(
        0,
        Number(actualMinutesByDate[dateKey] ?? (
          !hasDateSpecificProgress && hasSingleExplicitDate ? fallbackTotalActual : 0
        )),
      );
      const estimated = Math.max(0, Number(task.estimatedMinutes || 0));
      const isDone = task.completed || (estimated > 0 ? dateActual >= estimated : dateActual > 0);
      occurrences.push({
        dateKey,
        taskId: task.id,
        taskTitle: task.title,
        completed: isDone,
        estimatedMinutes: task.estimatedMinutes,
        actualMinutes: dateActual,
      });
    };

    if (Array.isArray(task.dates) && task.dates.length > 0) {
      for (const dateStr of task.dates) {
        const dt = parseDateLike(dateStr);
        if (dt) {
          append(dt);
        }
      }
      continue;
    }

    if (task.date || task.dueDate) {
      const dt = parseDateLike(task.date || task.dueDate);
      if (dt) {
        append(dt);
      }
      continue;
    }

    const weekdays = Array.isArray(task.weekdays) && task.weekdays.length > 0
      ? task.weekdays
      : (() => {
          const inferred = inferWeekdayFromTitle(task.title || "");
          return inferred === null ? [] : [inferred];
        })();

    if (weekdays.length > 0) {
      const start = parseDateLike(task.startDate) || today;
      const inferredWeeks = inferRepeatWeeksFromTitle(task.title || "");
      const repeatWeeks = Math.max(1, Number(task.repeatCount || inferredWeeks || 3));

      for (let week = 0; week < repeatWeeks; week += 1) {
        for (const weekday of weekdays) {
          const cursor = addDays(start, week * 7);
          const delta = (weekday - cursor.getDay() + 7) % 7;
          append(addDays(cursor, delta));
        }
      }
    }
  }

  return occurrences;
}

function buildMonthGrid(displayMonth: Date): Date[] {
  const firstDay = monthStart(displayMonth);
  const startOffset = firstDay.getDay();
  const gridStart = addDays(firstDay, -startOffset);
  return Array.from({ length: 42 }, (_, idx) => addDays(gridStart, idx));
}

export default function DailyPlanCalendar({ plan, onStartFocusDay }: DailyPlanCalendarProps) {
  const { locale } = useI18n();
  const tasks = plan?.tasks ?? [];
  const completed = tasks.filter((task) => task.completed).length;
  const total = tasks.length;

  const occurrences = useMemo(() => buildOccurrences(plan), [plan]);

  const occurrenceMap = useMemo(() => {
    const map = new Map<string, CalendarOccurrence[]>();
    for (const item of occurrences) {
      if (!map.has(item.dateKey)) {
        map.set(item.dateKey, []);
      }
      map.get(item.dateKey)?.push(item);
    }
    return map;
  }, [occurrences]);

  const daySummaryMap = useMemo(() => {
    const map = new Map<string, DaySummary>();
    for (const [dateKey, items] of occurrenceMap.entries()) {
      const totalMinutes = items.reduce((acc, item) => acc + (item.estimatedMinutes || 0), 0);
      const completedMinutes = items.reduce((acc, item) => {
        const actual = Math.max(0, Number(item.actualMinutes || 0));
        const estimated = Math.max(0, Number(item.estimatedMinutes || 0));
        if (estimated > 0) {
          return acc + Math.min(actual, estimated);
        }
        return acc + actual;
      }, 0);
      const completedCount = items.filter((item) => item.completed).length;
      map.set(dateKey, {
        items,
        totalMinutes,
        completedMinutes,
        completedCount,
        allDone: items.length > 0 && completedCount === items.length,
      });
    }
    return map;
  }, [occurrenceMap]);

  const firstOccurrenceDate = useMemo(() => {
    if (occurrences.length === 0) {
      return new Date();
    }
    const sorted = [...occurrences].sort((a, b) => (a.dateKey < b.dateKey ? -1 : 1));
    return parseDateLike(sorted[0].dateKey) || new Date();
  }, [occurrences]);

  const [displayMonth, setDisplayMonth] = useState<Date>(monthStart(firstOccurrenceDate));
  const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);

  useEffect(() => {
    setDisplayMonth(monthStart(firstOccurrenceDate));
    setSelectedDateKey(dateKeyOf(firstOccurrenceDate));
  }, [firstOccurrenceDate]);

  const monthGrid = useMemo(() => buildMonthGrid(displayMonth), [displayMonth]);

  const deadlineDate = useMemo(() => {
    const meta = plan as PlanData & {
      deadline?: string;
      dueDate?: string;
      endDate?: string;
      meta?: { deadline?: string };
    };
    return parseDateLike(meta?.deadline || meta?.dueDate || meta?.endDate || meta?.meta?.deadline || "");
  }, [plan]);

  const selectedDateItems = selectedDateKey ? occurrenceMap.get(selectedDateKey) || [] : [];

  const weekdayLabels = locale === "zh"
    ? ["日", "一", "二", "三", "四", "五", "六"]
    : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const monthLabel = displayMonth.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "long",
  });

  return (
    <section className="rounded-2xl border border-slate-200 bg-gradient-to-br from-surface-elevated/90 via-slate-50/85 to-teal-50/70 p-4 backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          {locale === "zh" ? "每日任务" : "Daily Mission"}
        </h3>
        <span className="rounded-full bg-white/85 px-2.5 py-0.5 text-[11px] text-slate-500">
          {locale === "zh" ? "月历总览" : "Monthly Overview"}
        </span>
      </div>

      <div className="mb-2 flex items-center justify-between rounded-xl border border-slate-200 bg-white/75 px-2 py-1.5">
        <button
          onClick={() => setDisplayMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
          aria-label={locale === "zh" ? "上个月" : "Previous Month"}
          className="rounded-lg bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {locale === "zh" ? "上月" : "Prev"}
        </button>
        <p className="text-sm font-semibold text-slate-700">{monthLabel}</p>
        <button
          onClick={() => setDisplayMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
          aria-label={locale === "zh" ? "下个月" : "Next Month"}
          className="rounded-lg bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {locale === "zh" ? "下月" : "Next"}
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1 text-[11px] text-slate-500">
        {weekdayLabels.map((label) => (
          <div key={label} className="text-center">{label}</div>
        ))}
      </div>

      <div className="mt-1 grid grid-cols-7 gap-1.5">
        {monthGrid.map((day) => {
          const key = dateKeyOf(day);
          const inMonth = day.getMonth() === displayMonth.getMonth();
          const summary = daySummaryMap.get(key);
          const items = summary?.items || [];
          const isDone = Boolean(summary?.allDone);
          const isSelected = selectedDateKey === key;
          const isDeadline = deadlineDate ? dateKeyOf(deadlineDate) === key : false;

          return (
            <div
              key={key}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedDateKey(key)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelectedDateKey(key);
                }
              }}
              className={`relative flex aspect-square cursor-pointer flex-col items-start justify-between rounded-lg border p-1.5 text-[11px] transition-all ${
                inMonth ? "text-slate-700" : "text-slate-400"
              } ${
                items.length === 0
                  ? "border-slate-200 bg-white/65"
                  : isDone
                    ? "border-emerald-300 bg-emerald-100/65 text-emerald-800"
                    : "border-rose-300 bg-rose-100/70 text-rose-800"
              } ${isDeadline ? "ring-1 ring-warning" : ""} ${isSelected ? "ring-2 ring-accent" : ""}`}
            >
              <div className="flex w-full items-center justify-between">
                <span className="font-medium">{day.getDate()}</span>
                {items.length > 0 ? (
                  <span className="text-[12px] leading-none drop-shadow-sm">
                    {isDone ? "✅" : "❌"}
                  </span>
                ) : null}
              </div>
              <div className="mt-1 w-full text-[10px] leading-tight">
                {items.length > 0 ? (
                  <div className="w-full">
                    <div className="mb-0.5 flex justify-between text-[9px] opacity-80">
                      <span>{summary?.completedMinutes || 0}m</span>
                      <span>{summary?.totalMinutes || 0}m</span>
                    </div>
                    <div className="h-1 w-full overflow-hidden rounded-full bg-black/10">
                      <div
                        className={`h-full ${isDone ? "bg-emerald-500" : "bg-rose-500"} transition-all`}
                        style={{
                          width: `${
                            (summary?.totalMinutes || 0) > 0
                              ? Math.min(100, ((summary?.completedMinutes || 0) / (summary?.totalMinutes || 1)) * 100)
                              : ((summary?.completedMinutes || 0) > 0 ? 100 : 0)
                          }%`,
                        }}
                      />
                    </div>
                  </div>
                ) : (
                  <p className="opacity-60">-</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-3 rounded-xl border border-slate-200 bg-white/80 p-3 text-xs text-slate-600">
        {selectedDateItems.length > 0 ? (
          <div className="space-y-1">
            <p className="text-slate-500">{selectedDateKey}</p>
            {selectedDateItems.map((item) => (
              <div key={`${item.taskId}-${item.dateKey}`} className="flex items-center justify-between rounded-lg bg-slate-50 px-2 py-1.5">
                <p className="truncate pr-2">{item.taskTitle}</p>
                <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium flex items-center gap-1 ${item.completed ? "text-emerald-700 bg-emerald-100/50" : "text-rose-700 bg-rose-100/50"}`}>
                  {item.completed ? "✅ " + (locale === "zh" ? "已完成" : "Done") : "❌ " + (locale === "zh" ? "未完成" : "Pending")}
                </span>
              </div>
            ))}
            <button
              type="button"
              onClick={() => {
                if (!selectedDateKey || selectedDateItems.length === 0 || !onStartFocusDay) {
                  return;
                }
                onStartFocusDay({ dateKey: selectedDateKey, tasks: selectedDateItems });
              }}
              className="group mt-3 w-full rounded-xl border border-teal-200/70 bg-gradient-to-r from-cyan-100 via-teal-100 to-emerald-100 px-3 py-2.5 text-center text-sm font-semibold text-slate-800 shadow-[0_10px_25px_-16px_rgba(16,185,129,0.85)] transition-all hover:-translate-y-0.5 hover:from-cyan-200 hover:via-teal-200 hover:to-emerald-200 hover:shadow-[0_14px_30px_-14px_rgba(16,185,129,0.95)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!selectedDateKey || selectedDateItems.length === 0 || !onStartFocusDay}
            >
              <span className="inline-flex items-center gap-1">
                <span className="transition-transform group-hover:translate-x-0.5">🚀</span>
                {locale === "zh" ? "开始今天的专注" : "Start Focus for Today"}
              </span>
            </button>
          </div>
        ) : (
          <p>{locale === "zh" ? "点击有标记的日期可查看任务详情并发起专注。" : "Click a marked date to inspect tasks and start focus."}</p>
        )}
      </div>

      <div className="mt-4 text-xs text-slate-500">{completed}/{total}</div>
    </section>
  );
}
