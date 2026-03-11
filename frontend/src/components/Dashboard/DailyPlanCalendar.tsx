import { useEffect, useMemo, useState } from "react";
import type { PlanData, PlanTask } from "@/lib/protocol";
import { useI18n } from "@/lib/i18n";

type ViewMode = "calendar" | "task" | "progress";

interface DailyPlanCalendarProps {
  plan: PlanData | null;
}

interface CalendarOccurrence {
  dateKey: string;
  taskTitle: string;
  completed: boolean;
  estimatedMinutes?: number;
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

function detectViewMode(plan: PlanData | null): ViewMode {
  if (!plan) {
    return "task";
  }

  const data = plan as PlanData & {
    planType?: string;
    deadline?: string;
    dueDate?: string;
    endDate?: string;
    meta?: { type?: string; deadline?: string };
  };

  const explicitType = String(data.planType || data.meta?.type || "").toLowerCase();
  if (["calendar", "weekly", "recurring", "schedule"].includes(explicitType)) {
    return "calendar";
  }
  if (["deadline", "progress", "sprint"].includes(explicitType)) {
    return "progress";
  }
  if (["task", "one-time", "single"].includes(explicitType)) {
    return "task";
  }

  const tasks = plan.tasks ?? [];
  const hasRecurringSignal = tasks.some((task) => {
    const t = task as PlanTask & {
      weekdays?: number[];
      repeatCount?: number;
      recurrence?: string;
      date?: string;
      dates?: string[];
      startDate?: string;
      endDate?: string;
    };
    const title = String(task.title || "").toLowerCase();
    return (
      Array.isArray(t.weekdays) ||
      typeof t.repeatCount === "number" ||
      Boolean(t.recurrence) ||
      Array.isArray(t.dates) ||
      /每周|weekly|every\s+(mon|tue|wed|thu|fri|sat|sun)/i.test(title)
    );
  });

  if (hasRecurringSignal) {
    return "calendar";
  }

  const hasDeadline = Boolean(data.deadline || data.dueDate || data.endDate || data.meta?.deadline);
  if (hasDeadline) {
    return "progress";
  }

  return "task";
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
      recurrence?: string;
      startDate?: string;
      endDate?: string;
    };

    const append = (date: Date) => {
      occurrences.push({
        dateKey: dateKeyOf(date),
        taskTitle: task.title,
        completed: task.completed,
        estimatedMinutes: task.estimatedMinutes,
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
      continue;
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

export default function DailyPlanCalendar({ plan }: DailyPlanCalendarProps) {
  const { locale } = useI18n();
  const mode = useMemo(() => detectViewMode(plan), [plan]);
  const tasks = plan?.tasks ?? [];
  const completed = tasks.filter((task) => task.completed).length;
  const total = tasks.length;
  const progressRatio = total > 0 ? completed / total : 0;

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

  const firstOccurrenceDate = useMemo(() => {
    if (occurrences.length === 0) {
      return new Date();
    }
    const sorted = [...occurrences].sort((a, b) => (a.dateKey < b.dateKey ? -1 : 1));
    return parseDateLike(sorted[0].dateKey) || new Date();
  }, [occurrences]);

  const [displayMonth, setDisplayMonth] = useState<Date>(monthStart(firstOccurrenceDate));
  const [hoveredDateKey, setHoveredDateKey] = useState<string | null>(null);

  useEffect(() => {
    setDisplayMonth(monthStart(firstOccurrenceDate));
  }, [firstOccurrenceDate]);

  const monthGrid = useMemo(() => buildMonthGrid(displayMonth), [displayMonth]);

  const deadlineDate = useMemo(() => {
    const meta = plan as PlanData & { deadline?: string; dueDate?: string; endDate?: string; meta?: { deadline?: string } };
    return parseDateLike(meta?.deadline || meta?.dueDate || meta?.endDate || meta?.meta?.deadline || "");
  }, [plan]);

  const selectedDateItems = hoveredDateKey ? occurrenceMap.get(hoveredDateKey) || [] : [];

  const weekdayLabels = locale === "zh"
    ? ["日", "一", "二", "三", "四", "五", "六"]
    : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const monthLabel = displayMonth.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "long",
  });

  return (
    <section className="rounded-2xl border border-slate-200 bg-surface-elevated/70 p-4 backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          {locale === "zh" ? "每日任务" : "Daily Mission"}
        </h3>
        <span className="rounded bg-slate-50 px-2 py-0.5 text-[11px] text-slate-500">
          {mode === "calendar"
            ? (locale === "zh" ? "自动视图: 日历" : "Auto View: Calendar")
            : mode === "progress"
              ? (locale === "zh" ? "自动视图: 进度" : "Auto View: Progress")
              : (locale === "zh" ? "自动视图: 任务" : "Auto View: Task")}
        </span>
      </div>

      {mode === "calendar" ? (
        <>
          <div className="mb-2 flex items-center justify-between">
            <button
              onClick={() => setDisplayMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
              className="rounded bg-slate-50 px-2 py-0.5 text-xs text-slate-600 hover:bg-black/30"
            >
              {locale === "zh" ? "上月" : "Prev"}
            </button>
            <p className="text-sm text-slate-700">{monthLabel}</p>
            <button
              onClick={() => setDisplayMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
              className="rounded bg-slate-50 px-2 py-0.5 text-xs text-slate-600 hover:bg-black/30"
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
              const items = occurrenceMap.get(key) || [];
              const isDone = items.length > 0 && items.every((item) => item.completed);
              const isDeadline = deadlineDate ? dateKeyOf(deadlineDate) === key : false;
              return (
                <div
                  key={key}
                  onMouseEnter={() => setHoveredDateKey(key)}
                  onMouseLeave={() => setHoveredDateKey((current) => (current === key ? null : current))}
                  className={`relative flex aspect-square items-center justify-center rounded-md text-[11px] ${
                    inMonth ? "text-slate-700" : "text-slate-400"
                  } ${
                    items.length === 0
                      ? "bg-slate-100"
                      : isDone
                        ? "bg-success/25 text-success"
                        : "bg-accent/20 text-accent"
                  } ${isDeadline ? "ring-1 ring-warning" : ""}`}
                >
                  {day.getDate()}
                  {items.length > 0 ? <span className="absolute bottom-1 h-1 w-1 rounded-full bg-current" /> : null}
                </div>
              );
            })}
          </div>

          <div className="mt-3 min-h-12 rounded-lg bg-slate-50 p-2 text-xs text-slate-600">
            {selectedDateItems.length > 0 ? (
              <div className="space-y-1">
                <p className="text-slate-500">{hoveredDateKey}</p>
                {selectedDateItems.map((item, index) => (
                  <p key={`${item.taskTitle}-${index}`}>
                    {item.taskTitle}
                    {item.estimatedMinutes ? ` (${item.estimatedMinutes}m)` : ""}
                  </p>
                ))}
              </div>
            ) : (
              <p>{locale === "zh" ? "悬浮有标记的日期可查看任务详情" : "Hover marked dates to preview task details"}</p>
            )}
          </div>
        </>
      ) : null}

      {mode === "progress" ? (
        <>
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs text-slate-500">{locale === "zh" ? "已完成天数" : "Completed Days"}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-700">
              {completed}
              <span className="ml-1 text-sm text-slate-500">/ {Math.max(total, 1)}</span>
            </p>
            <p className="mt-2 text-xs text-slate-500">
              {locale === "zh" ? "DDL" : "Deadline"}: {deadlineDate ? deadlineDate.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US") : (locale === "zh" ? "未设置" : "Not set")}
            </p>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-gradient-to-r from-accent to-success" style={{ width: `${Math.round(progressRatio * 100)}%` }} />
          </div>
        </>
      ) : null}

      {mode === "task" ? (
        <div className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
          {tasks[0]
            ? `${tasks[0].title}${tasks[0].estimatedMinutes ? ` (${tasks[0].estimatedMinutes}m)` : ""}`
            : locale === "zh"
              ? "当前还没有一次性任务描述。"
              : "No one-time task description yet."}
        </div>
      ) : null}

      <div className="mt-4 text-xs text-slate-500">{completed}/{total}</div>
    </section>
  );
}
