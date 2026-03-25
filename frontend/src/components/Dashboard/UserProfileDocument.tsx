import { useMemo } from "react";

interface UserProfileDocumentProps {
  locale: "zh" | "en";
  content: string;
  updatedAt?: string | null;
  maxChars?: number;
  loading?: boolean;
}

interface ProfileSection {
  label: string;
  icon: string;
  lines: string[];
}

const SECTION_KEYWORDS_ZH: [string, RegExp][] = [
  ["身份背景", /学校|年级|专业|大学|高中|初中|班级|学历|姓名|名字|称呼|叫|岁|性别|身份/],
  ["学习习惯", /习惯|作息|时间|起床|睡觉|早上|晚上|日程|每天|每周|复习|预习|偏好|喜欢.*学|方式|方法|风格/],
  ["困难与挑战", /困难|难|走神|分心|拖延|焦虑|压力|挑战|弱点|不擅长|容易/],
  ["激励偏好", /激励|奖励|鼓励|动力|目标|惩罚|罚|喜欢被|讨厌被|称赞|夸/],
];

const SECTION_ICONS: Record<string, string> = {
  "身份背景": "👤",
  "学习习惯": "📖",
  "困难与挑战": "⚡",
  "激励偏好": "🎯",
  "其他": "📝",
  "Identity": "👤",
  "Study Habits": "📖",
  "Challenges": "⚡",
  "Motivation": "🎯",
  "Other": "📝",
};

function classifyLines(content: string, locale: "zh" | "en"): ProfileSection[] {
  const raw = content
    .split(/\r?\n/)
    .map((l) => l.replace(/^[-•]\s*/, "").trim())
    .filter(Boolean);

  if (raw.length === 0) return [];

  const buckets = new Map<string, string[]>();
  const otherLabel = locale === "zh" ? "其他" : "Other";

  for (const line of raw) {
    let matched = false;
    for (const [label, re] of SECTION_KEYWORDS_ZH) {
      if (re.test(line)) {
        const displayLabel = locale === "zh" ? label : { "身份背景": "Identity", "学习习惯": "Study Habits", "困难与挑战": "Challenges", "激励偏好": "Motivation" }[label] ?? label;
        if (!buckets.has(displayLabel)) buckets.set(displayLabel, []);
        buckets.get(displayLabel)!.push(line);
        matched = true;
        break;
      }
    }
    if (!matched) {
      if (!buckets.has(otherLabel)) buckets.set(otherLabel, []);
      buckets.get(otherLabel)!.push(line);
    }
  }

  return Array.from(buckets.entries()).map(([label, lines]) => ({
    label,
    icon: SECTION_ICONS[label] ?? "📝",
    lines,
  }));
}

export default function UserProfileDocument({
  locale,
  content,
  updatedAt,
  maxChars = 4000,
  loading = false,
}: UserProfileDocumentProps) {
  const sections = useMemo(() => classifyLines(content, locale), [content, locale]);
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
          {sections.length > 0 ? (
            <div className="max-h-48 space-y-2.5 overflow-y-auto rounded-xl border border-slate-200 bg-white/80 p-3">
              {sections.map((sec) => (
                <div key={sec.label}>
                  <p className="mb-1 flex items-center gap-1 text-[11px] font-semibold text-slate-500">
                    <span>{sec.icon}</span>
                    <span>{sec.label}</span>
                  </p>
                  <ul className="space-y-0.5 pl-4">
                    {sec.lines.map((line, idx) => (
                      <li key={idx} className="list-disc text-xs leading-relaxed text-slate-600">
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white/80 p-3 text-xs leading-relaxed text-slate-600">
              {locale === "zh"
                ? "暂无画像内容。开始几轮专注后，系统会逐步补全你的学习习惯、偏好和有效激励方式。"
                : "No profile content yet. After several focus sessions, the system will gradually infer your habits, preferences, and effective motivation style."}
            </div>
          )}

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