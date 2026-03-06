/* ────────────────────────────────────────────────
 *  TextInput  –  Fallback text input box
 * ──────────────────────────────────────────────── */
import { useState, type KeyboardEvent } from "react";
import { useI18n } from "@/lib/i18n";

interface Props {
  onSend: (text: string) => void;
}

export default function TextInput({ onSend }: Props) {
  const [value, setValue] = useState("");
  const { t } = useI18n();

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-white/5 px-4 py-3">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder={t("focus.sendPlaceholder")}
          className="flex-1 rounded-xl bg-surface-elevated px-4 py-2.5 text-sm text-white outline-none ring-1 ring-white/5 transition-all placeholder:text-white/30 focus:ring-accent/40"
        />
        <button
          onClick={handleSubmit}
          disabled={!value.trim()}
          className="rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-30"
        >
          {t("focus.send")}
        </button>
      </div>
    </div>
  );
}
