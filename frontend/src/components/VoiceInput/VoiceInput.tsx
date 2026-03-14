/* ────────────────────────────────────────────────
 *  VoiceInput  –  Interactive voice input indicator + mic toggle
 *
 *  Visual states:
 *    listening  → pulsing accent ring + "正在聆听" label
 *    idle       → subtle breathing dot  + "待命" label
 *    muted      → crossed-out mic icon  + "已静音" label
 *    off        → dim icon              + "语音未开" label
 *
 *  Clicking toggles micMuted. The actual VAD start/stop is driven
 *  by useVAD hook at a higher level — this component only reads
 *  state and provides the mute toggle.
 * ──────────────────────────────────────────────── */
import { useMediaStore } from "@/stores/mediaStore";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useI18n } from "@/lib/i18n";

export type VoiceState = "listening" | "idle" | "muted" | "off";

export default function VoiceInput() {
  const {
    isListening,
    vadActive,
    micMuted,
    micAudioLevel,
    micGranted,
    micSupported,
    toggleMicMute,
    requestMicrophone,
  } = useMediaStore();
  const isAgentSpeaking = useChatStore((s) => s.isAgentSpeaking);
  const supervisionState = useSessionStore((s) => s.supervisionState);
  const isPaused = supervisionState === "paused";
  const { t } = useI18n();

  // Determine visual state
  const state: VoiceState =
    micMuted || isAgentSpeaking || isPaused
      ? "muted"
      : isListening
        ? "listening"
        : vadActive
          ? "idle"
          : "off";

  // Audio level drives the ring scale (0→1 mapped to 1.0→1.6)
  const ringScale = state === "listening" ? 1 + micAudioLevel * 0.6 : 1;

  const label =
    state === "listening"
      ? t("voice.listening")
      : state === "muted"
        ? t("voice.muted")
        : state === "idle"
          ? t("voice.idle")
          : t("voice.off");

  const handleClick = async () => {
    if (!micGranted) {
      if (micSupported) {
        await requestMicrophone();
      }
      return;
    }
    toggleMicMute();
  };

  return (
    <div className="flex flex-col items-center gap-1.5">
      {/* Main button */}
      <button
        onClick={handleClick}
        className="group relative flex items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        title={label}
        aria-label={label}
      >
        {/* Audio level ring — listening state */}
        {state === "listening" && (
          <span
            className="absolute h-14 w-14 rounded-full bg-accent/25 transition-transform duration-75"
            style={{ transform: `scale(${ringScale})` }}
          />
        )}

        {/* Breathing ring — idle/standby */}
        {state === "idle" && (
          <span className="absolute h-12 w-12 animate-breathing rounded-full bg-slate-100" />
        )}

        {/* Mic icon circle */}
        <div
          className={`relative z-10 flex h-11 w-11 items-center justify-center rounded-full transition-all duration-200 ${
            state === "listening"
              ? "bg-accent text-slate-800 shadow-lg shadow-accent/30"
              : state === "muted"
                ? "bg-slate-200/50 text-slate-400"
                : state === "idle"
                  ? "bg-surface-elevated text-slate-500 group-hover:text-slate-700"
                  : "bg-surface-elevated text-slate-300"
          }`}
        >
          <svg
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            {state === "muted" ? (
              <>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"
                  opacity={0.3}
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19 10v2a7 7 0 01-14 0v-2M12 19v4m-4 0h8"
                  opacity={0.3}
                />
                {/* Slash line */}
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 3l18 18"
                  strokeWidth={2.5}
                />
              </>
            ) : (
              <>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19 10v2a7 7 0 01-14 0v-2M12 19v4m-4 0h8"
                />
              </>
            )}
          </svg>
        </div>
      </button>

      {/* Status label */}
      <span
        className={`text-xs transition-colors ${
          state === "listening"
            ? "font-medium text-accent"
            : state === "muted"
              ? "text-slate-300"
              : "text-slate-400"
        }`}
      >
        {label}
      </span>
    </div>
  );
}
