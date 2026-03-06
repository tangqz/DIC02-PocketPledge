/* ────────────────────────────────────────────────
 *  App  –  Top-level state machine router + global wiring
 *
 *  Responsibilities at this level:
 *   • WebSocket connection (persistent across all layouts)
 *   • VAD initialization (mic → audio → WS)
 *   • Provide `send` function via React context so any layout
 *     can send TxMessages without prop-drilling
 * ──────────────────────────────────────────────── */
import { createContext, useContext, useCallback, useMemo } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useMediaStore } from "@/stores/mediaStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useVAD } from "@/hooks/useVAD";
import SetupLayout from "@/components/Layout/SetupLayout";
import FocusLayout from "@/components/Layout/FocusLayout";
import SummaryLayout from "@/components/Layout/SummaryLayout";
import type { TxMessage } from "@/lib/protocol";

// ── Send context ──
type SendFn = (msg: TxMessage) => void;
const SendContext = createContext<SendFn>(() => {
  console.warn("[SendContext] No provider — message dropped");
});

/** Hook for child components to send WS messages */
export function useSend(): SendFn {
  return useContext(SendContext);
}

export default function App() {
  const supervisionState = useSessionStore((s) => s.supervisionState);
  const micMuted = useMediaStore((s) => s.micMuted);
  const micGranted = useMediaStore((s) => s.micGranted);

  // ── WebSocket (global, persistent) ──
  const { send } = useWebSocket();

  // ── VAD → WS bridge ──
  // When user finishes a speech segment, stream it to the backend
  // as mic-audio-end with empty images (images can be added by
  // snapshot logic separately).
  const handleSpeechEnd = useCallback(
    (audio: Float32Array) => {
      if (micMuted) return; // user toggled mute during speech

      // Send audio chunks for streaming (entire segment at once for now)
      const samples = Array.from(audio);
      const CHUNK_SIZE = 4096;
      for (let i = 0; i < samples.length; i += CHUNK_SIZE) {
        send({
          type: "mic-audio-data",
          audio: samples.slice(i, i + CHUNK_SIZE),
        });
      }

      // Signal end-of-speech with optional snapshots
      send({
        type: "mic-audio-end",
        images: [], // TODO: attach periodic screenshots here
      });
    },
    [send, micMuted],
  );

  useVAD({
    onSpeechEnd: handleSpeechEnd,
    enabled: micGranted && !micMuted,
  });

  // Memoize the send value to avoid unnecessary re-renders
  const sendValue = useMemo(() => send, [send]);

  return (
    <SendContext.Provider value={sendValue}>
      <div className="h-full w-full bg-surface">
        {supervisionState === "setup" && <SetupLayout />}
        {(supervisionState === "active" || supervisionState === "paused") && (
          <FocusLayout />
        )}
        {supervisionState === "completed" && <SummaryLayout />}
      </div>
    </SendContext.Provider>
  );
}
