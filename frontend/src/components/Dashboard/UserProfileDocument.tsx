import { useMemo } from "react";

interface UserProfileDocumentProps {
  locale: "zh" | "en";
  content: string;
  updatedAt?: string | null;
  maxChars?: number;
  loading?: boolean;
}

function buildHighlights(content: string): string[] {
  const normalized = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (normalized.length === 0) {
    return [];
  }

  return normalized.slice(0, 4);
}

export default function UserProfileDocument({
  locale,
  content,
  updatedAt,
  maxChars = 4000,
  loading = false,
}: UserProfileDocumentProps) {
  const highlights = useMemo(() => buildHighlights(content), [content]);
  const usedChars = content.length;
  const usageRatio = Math.min(100, Math.round((usedChars / Math.max(maxChars, 1)) * 100));

  return (
    <section className="rounded-2xl border border-slate-200 bg-gradient-to-br from-surface-elevated/90 via-slate-50 to-amber-50/60 p-4 backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          {locale === "zh" ? "用户画像文档" : "User Profile Document"}
        </h3>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
          {locale === "zh" ? "记忆侧写" : "Persona Snapshot"}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2 rounded-xl bg-white/70 p-3">
          <div className="h-3 w-32 animate-pulse rounded bg-slate-200" />
          <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-slate-200" />
        </div>
      ) : (
        <>
          {highlights.length > 0 ? (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {highlights.map((line, index) => (
                <span
                  key={`${line}-${index}`}
                  className="max-w-full truncate rounded-full border border-slate-200 bg-white/85 px-2.5 py-1 text-[11px] text-slate-600"
                  title={line}
                >
                  {line}
                </span>
              ))}
            </div>
          ) : null}

          <div className="max-h-40 overflow-y-auto rounded-xl border border-slate-200 bg-white/80 p-3 text-xs leading-relaxed text-slate-600">
            {content.trim().length > 0
              ? content
              : locale === "zh"
                ? "暂无画像内容。开始几轮专注后，系统会逐步补全你的学习习惯、偏好和有效激励方式。"
                : "No profile content yet. After several focus sessions, the system will gradually infer your habits, preferences, and effective motivation style."}
          </div>

          <div className="mt-3 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-slate-500">
              <span>{locale === "zh" ? "文档容量" : "Document Usage"}</span>
              <span>{usedChars}/{maxChars}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500"
                style={{ width: `${usageRatio}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400">
              {locale === "zh"
                ? `最近更新：${updatedAt ? new Date(updatedAt).toLocaleString() : "暂无"}`
                : `Last updated: ${updatedAt ? new Date(updatedAt).toLocaleString() : "N/A"}`}
            </p>
          </div>
        </>
      )}
    </section>
  );
}