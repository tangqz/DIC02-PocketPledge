/* ────────────────────────────────────────────────
 *  App  –  Top-level auth gate + state machine router + global wiring
 *
 *  Responsibilities at this level:
 *   • Auth guard: show LoginPage until a valid JWT exists
 *   • WebSocket connection (persistent across all layouts)
 *   • VAD initialization (mic → audio → WS)
 *   • Provide `send` function via React context so any layout
 *     can send TxMessages without prop-drilling
 * ──────────────────────────────────────────────── */
import { createContext, useContext, useCallback, useMemo, useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useMediaStore } from "@/stores/mediaStore";
import { useAuthStore } from "@/stores/authStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useCharacterStore } from "@/stores/characterStore";
import { useChatStore } from "@/stores/chatStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useVAD } from "@/hooks/useVAD";
import { captureImagesFromStreams, useSnapshot } from "@/hooks/useSnapshot";
import { useI18n } from "@/lib/i18n";
import LoginPage from "@/components/Auth/LoginPage";
import SetupLayout from "@/components/Layout/SetupLayout";
import FocusLayout from "@/components/Layout/FocusLayout";
import SummaryLayout from "@/components/Layout/SummaryLayout";
import type { RxMessage, SnapshotImage, TxMessage } from "@/lib/protocol";

// ── Send context ──
type SendFn = (msg: TxMessage) => void;
const SendContext = createContext<SendFn>(() => {
  console.warn("[SendContext] No provider — message dropped");
});

/** Hook for child components to send WS messages */
export function useSend(): SendFn {
  return useContext(SendContext);
}

/** Inner app — only rendered when authenticated */
function AuthenticatedApp() {
  const supervisionState = useSessionStore((s) => s.supervisionState);
  const degradedMode = useSessionStore((s) => s.degradedMode);
  const micMuted = useMediaStore((s) => s.micMuted);
  const micGranted = useMediaStore((s) => s.micGranted);
  const cameraGranted = useMediaStore((s) => s.cameraGranted);
  const screenGranted = useMediaStore((s) => s.screenGranted);
  const snapshotInterval = useMediaStore((s) => s.snapshotInterval);
  const setSnapshotActive = useMediaStore((s) => s.setSnapshotActive);
  const cameraStream = useMediaStore((s) => s.cameraStream);
  const screenStream = useMediaStore((s) => s.screenStream);
  const requestCamera = useMediaStore((s) => s.requestCamera);
  const requestScreenShare = useMediaStore((s) => s.requestScreenShare);
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const setBalance = useSessionStore((s) => s.setBalance);
  const setDegradedMode = useSessionStore((s) => s.setDegradedMode);
  const selectedCharacterId = useCharacterStore((s) => s.selectedCharacterId);
  const setSelectedCharacterId = useCharacterStore((s) => s.setSelectedCharacterId);
  const { locale } = useI18n();
  const lastSentCharacterRef = useRef<string>("");

  // ── WebSocket (global, persistent) ──
  const captureVisualContext = useCallback(async (
    sources: Array<"camera" | "screen">,
  ): Promise<{ images: SnapshotImage[]; error?: string }> => {
    const wantsCamera = sources.includes("camera");
    const wantsScreen = sources.includes("screen");

    if (wantsCamera && !useMediaStore.getState().cameraStream) {
      const granted = await requestCamera();
      if (!granted) {
        return { images: [], error: "camera permission denied" };
      }
    }

    if (wantsScreen && !useMediaStore.getState().screenStream) {
      const granted = await requestScreenShare();
      if (!granted) {
        return { images: [], error: "screen share denied" };
      }
    }

    await new Promise((resolve) => window.setTimeout(resolve, 180));

    const images = await captureImagesFromStreams({
      cameraEnabled: wantsCamera,
      screenEnabled: wantsScreen,
      cameraStream: useMediaStore.getState().cameraStream,
      screenStream: useMediaStore.getState().screenStream,
    });
    if (images.length === 0) {
      return { images: [], error: "no images captured" };
    }
    return { images };
  }, [requestCamera, requestScreenShare]);

  const { send } = useWebSocket({
    onMessage: (msg: RxMessage) => {
      if (msg.type === "audio") {
        useAvatarStore.getState().enqueueAudioMessage(msg);
        return;
      }

      if (msg.type === "model-info") {
        useAvatarStore.getState().setModelInfo(msg.model_info);
        if (msg.character_id && msg.character_id !== useCharacterStore.getState().selectedCharacterId) {
          setSelectedCharacterId(msg.character_id);
        }
        return;
      }

      if (msg.type === "control") {
        if (msg.command === "downgrade") {
          useAvatarStore.getState().clearAudioMessages();
          setDegradedMode(true);
          return;
        }

        if (msg.command === "request-visual-context") {
          const requestId = msg.payload?.requestId ?? "unknown";
          const prompt = msg.payload?.prompt ?? "";
          const sources = msg.payload?.sources ?? ["screen", "camera"];

          void captureVisualContext(sources).then(({ images, error }) => {
            send({
              type: "capture-context-result",
              requestId,
              prompt,
              images,
              error,
            });
          });
        }

        if (msg.command === "chat-cleared") {
          useChatStore.getState().clearMessages();
          useAvatarStore.getState().clearAudioMessages();
          return;
        }
      }
    },
  });

  useEffect(() => {
    send({ type: "set-locale", locale });
  }, [locale, send]);

  useEffect(() => {
    if (!selectedCharacterId || selectedCharacterId === lastSentCharacterRef.current) {
      return;
    }
    lastSentCharacterRef.current = selectedCharacterId;
    send({ type: "set-character", characterId: selectedCharacterId });
  }, [selectedCharacterId, send]);

  // ── VAD → WS bridge ──
  const handleSpeechEnd = useCallback(
    (audio: Float32Array) => {
      if (micMuted) return;
      console.log("[Voice] Sending speech segment, samples=", audio.length);
      const samples = Array.from(audio);
      const CHUNK_SIZE = 4096;
      for (let i = 0; i < samples.length; i += CHUNK_SIZE) {
        send({
          type: "mic-audio-data",
          audio: samples.slice(i, i + CHUNK_SIZE),
        });
      }
      send({
        type: "mic-audio-end",
        images: [],
      });
      console.log("[Voice] Sent mic-audio-end");
    },
    [send, micMuted],
  );

  useVAD({
    onSpeechEnd: handleSpeechEnd,
    enabled: micGranted && !micMuted,
  });

  const snapshotEnabled =
    supervisionState === "active" && !degradedMode && (cameraGranted || screenGranted);

  useSnapshot({
    intervalMs: snapshotInterval * 1000,
    cameraEnabled: cameraGranted,
    screenEnabled: screenGranted,
    cameraStream,
    screenStream,
    active: snapshotEnabled,
    onCapture: (images) => {
      send({ type: "periodic-screenshot", images });
    },
  });

  useEffect(() => {
    setSnapshotActive(snapshotEnabled);
  }, [setSnapshotActive, snapshotEnabled]);

  useEffect(() => {
    if (typeof user?.balance === "number") {
      setBalance(user.balance);
      setDegradedMode(user.balance <= 0);
    }
  }, [setBalance, setDegradedMode, user?.balance]);

  const sendValue = useMemo(() => send, [send]);

  return (
    <SendContext.Provider value={sendValue}>
      <div className="h-full w-full bg-surface">
        {/* Logout button */}
        <button
          onClick={logout}
          className="fixed right-4 top-4 z-50 rounded-lg bg-white/10 px-3 py-1 text-sm text-white/70 backdrop-blur-sm hover:bg-white/20"
        >
          退出
        </button>

        {supervisionState === "setup" && <SetupLayout />}
        {(supervisionState === "active" || supervisionState === "paused") && (
          <FocusLayout />
        )}
        {supervisionState === "completed" && <SummaryLayout />}
      </div>
    </SendContext.Provider>
  );
}

export default function App() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const hydrate = useAuthStore((s) => s.hydrate);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const [ready, setReady] = useState(false);

  // On mount: restore token from localStorage and verify it
  useEffect(() => {
    hydrate();
    const stored = useAuthStore.getState().token;
    if (stored) {
      fetchMe().finally(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    if (token && user && user.balance === undefined) {
      fetchMe();
    }
  }, [fetchMe, token, user]);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900">
        <p className="text-white/50">加载中…</p>
      </div>
    );
  }

  if (!token || !user) {
    return <LoginPage />;
  }

  return <AuthenticatedApp />;
}
