import { useState, useCallback, useEffect } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useI18n } from "@/lib/i18n";
import { API_BASE } from "@/stores/authStore";

export default function CharitySlider() {
  const { charityRatio, setCharityRatio } = useSessionStore();
  const { t } = useI18n();
  const [localRatio, setLocalRatio] = useState(charityRatio);
  const [isUpdating, setIsUpdating] = useState(false);

  // Sync with store if it changes externally
  useEffect(() => {
    setLocalRatio(charityRatio);
  }, [charityRatio]);

  const updateBackend = useCallback(async (newRatio: number) => {
    setIsUpdating(true);
    try {
      const token = localStorage.getItem("sb_token");
      if (!token) return;

      const res = await fetch(`${API_BASE}/api/business/me/settings/charity-ratio`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ charity_ratio: newRatio })
      });

      if (!res.ok) {
        console.error("Failed to update charity ratio");
        // Revert on failure
        setLocalRatio(charityRatio);
      } else {
        setCharityRatio(newRatio);
      }
    } catch (err) {
      console.error(err);
      setLocalRatio(charityRatio);
    } finally {
      setIsUpdating(false);
    }
  }, [charityRatio, setCharityRatio]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalRatio(Number(e.target.value));
  };

  const handleMouseUp = () => {
    if (localRatio !== charityRatio) {
      updateBackend(localRatio);
    }
  };

  return (
    <div className="flex flex-col gap-1 w-48 text-xs text-slate-500">
      <div className="flex justify-between items-center px-1 font-medium">
        <span className="text-amber-500/80">{t("status.pool")} {100 - localRatio}%</span>
        <span className="text-emerald-500/80">{localRatio}% {t("status.charity")}</span>
      </div>
      <input
        type="range"
        min="0"
        max="100"
        value={localRatio}
        onChange={handleChange}
        onMouseUp={handleMouseUp}
        onTouchEnd={handleMouseUp}
        disabled={isUpdating}
        aria-label={t("status.charityRatio")}
        className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-slate-400 disabled:opacity-50"
      />
    </div>
  );
}
