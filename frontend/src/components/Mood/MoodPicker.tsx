import { useState, useCallback } from "react";
import { useAuthStore, API_BASE } from "@/stores/authStore";
import { useI18n } from "@/lib/i18n";

const MOODS = [
  { emoji: "😊", label: "happy", zh: "开心" },
  { emoji: "😢", label: "sad", zh: "难过" },
  { emoji: "😰", label: "anxious", zh: "焦虑" },
  { emoji: "😤", label: "angry", zh: "生气" },
  { emoji: "😴", label: "tired", zh: "疲惫" },
  { emoji: "😌", label: "calm", zh: "平静" },
  { emoji: "🥰", label: "loved", zh: "被爱" },
  { emoji: "😐", label: "neutral", zh: "一般" },
] as const;

interface MoodPickerProps {
  onClose?: () => void;
}

export default function MoodPicker({ onClose }: MoodPickerProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [intensity, setIntensity] = useState(3);
  const [context, setContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { locale } = useI18n();

  const submit = useCallback(async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      const token = useAuthStore.getState().token;
      await fetch(`${API_BASE}/api/business/me/mood`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          emotion: selected,
          intensity,
          context,
          source: "manual",
        }),
      });
      onClose?.();
    } catch (err) {
      console.error("Failed to submit mood:", err);
    } finally {
      setSubmitting(false);
    }
  }, [selected, intensity, context, onClose]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur-sm">
      <p className="mb-3 text-center text-sm font-medium text-slate-700">
        {locale === "zh" ? "你现在感觉怎么样？" : "How are you feeling?"}
      </p>

      {/* Emoji grid */}
      <div className="mb-3 grid grid-cols-4 gap-2">
        {MOODS.map((m) => (
          <button
            key={m.label}
            onClick={() => setSelected(m.label)}
            className={`flex flex-col items-center rounded-xl p-2 transition-all ${
              selected === m.label
                ? "scale-110 bg-violet-100 ring-2 ring-violet-400"
                : "bg-slate-50 hover:bg-slate-100"
            }`}
          >
            <span className="text-2xl">{m.emoji}</span>
            <span className="mt-0.5 text-[10px] text-slate-500">
              {locale === "zh" ? m.zh : m.label}
            </span>
          </button>
        ))}
      </div>

      {/* Intensity slider */}
      {selected && (
        <>
          <div className="mb-2">
            <label className="mb-1 block text-xs text-slate-500">
              {locale === "zh" ? `强度: ${intensity}/5` : `Intensity: ${intensity}/5`}
            </label>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={intensity}
              onChange={(e) => setIntensity(Number(e.target.value))}
              className="w-full accent-violet-500"
            />
          </div>

          {/* Optional context */}
          <input
            type="text"
            placeholder={locale === "zh" ? "想说点什么？（可选）" : "Any context? (optional)"}
            value={context}
            onChange={(e) => setContext(e.target.value)}
            maxLength={200}
            className="mb-3 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:border-violet-400 focus:outline-none"
          />

          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={submitting}
              className="flex-1 rounded-lg bg-violet-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
            >
              {submitting
                ? "..."
                : locale === "zh"
                  ? "记录"
                  : "Record"}
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="rounded-lg bg-slate-100 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-200"
              >
                {locale === "zh" ? "取消" : "Cancel"}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
