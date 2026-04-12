/* ────────────────────────────────────────────────
 *  App  –  WarmBuddy companion hub
 *
 *  Single layout: Auth gate → CompanionLayout.
 *  No session state machine — open page = start companion.
 * ──────────────────────────────────────────────── */
import { useCallback, useMemo, useEffect, useRef, useState } from "react";
import { useMediaStore } from "@/stores/mediaStore";
import { useAuthStore } from "@/stores/authStore";
import { useAvatarStore } from "@/stores/avatarStore";
import { useCharacterStore } from "@/stores/characterStore";
import { useChatStore } from "@/stores/chatStore";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useVAD } from "@/hooks/useVAD";
import { captureImagesFromStreams, useSnapshot } from "@/hooks/useSnapshot";
import { useI18n } from "@/lib/i18n";
import { SendContext } from "@/lib/sendContext";
import LoginPage from "@/components/Auth/LoginPage";
import CompanionLayout from "@/components/Layout/CompanionLayout";
import type { RxMessage, SnapshotImage } from "@/lib/protocol";

/** Inner app — only rendered when authenticated */
function AuthenticatedApp() {
  const hasSentPageOpenedRef = useRef(false);
  const micMuted = useMediaStore((s) => s.micMuted);
  const micGranted = useMediaStore((s) => s.micGranted);
  const cameraGranted = useMediaStore((s) => s.cameraGranted);
  const snapshotInterval = useMediaStore((s) => s.snapshotInterval);
  const setSnapshotActive = useMediaStore((s) => s.setSnapshotActive);
  const cameraStream = useMediaStore((s) => s.cameraStream);
  const requestCamera = useMediaStore((s) => s.requestCamera);
  const selectedCharacterId = useCharacterStore((s) => s.selectedCharacterId);
  const setSelectedCharacterId = useCharacterStore((s) => s.setSelectedCharacterId);
  const { locale } = useI18n();

  // ── Capture helper for <<CAPTURE>> requests ──
  const captureVisualContext = useCallback(async (
    sources: Array<"camera" | "screen">,
  ): Promise<{ images: SnapshotImage[]; error?: string }> => {
    if (!useMediaStore.getState().cameraStream) {
      const granted = await requestCamera();
      if (!granted) {
        return { images: [], error: "camera permission denied" };
      }
    }
    await new Promise((resolve) => window.setTimeout(resolve, 180));
    const images = await captureImagesFromStreams({
      cameraEnabled: sources.includes("camera"),
      screenEnabled: false,
      cameraStream: useMediaStore.getState().cameraStream,
      screenStream: null,
    });
    if (images.length === 0) {
      return { images: [], error: "no images captured" };
    }
    return { images };
  }, [requestCamera]);

  // ── WebSocket ──
  const { send } = useWebSocket({
    locale,
    onMessage: (msg: RxMessage) => {
      if (msg.type === "audio") {
        useAvatarStore.getState().enqueueAudioMessage(msg);
        return;
      }
      if (msg.type === "audio-stream-chunk") {
        useAvatarStore.getState().enqueueStreamChunk(msg.audio, msg.expression);
        return;
      }
      if (msg.type === "audio-stream-end") {
        useAvatarStore.getState().endAudioStream();
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
        if (msg.command === "set-expression") {
          useAvatarStore.getState().setCurrentExpression(String(msg.payload?.expression || "neutral"));
          return;
        }
        if (msg.command === "request-visual-context") {
          const requestId = typeof msg.payload?.requestId === "string" ? msg.payload.requestId : "unknown";
          const prompt = typeof msg.payload?.prompt === "string" ? msg.payload.prompt : "";
          const sourceCandidates = Array.isArray(msg.payload?.sources) ? msg.payload.sources : ["camera"];
          const sources = sourceCandidates.filter(
            (source): source is "camera" | "screen" => source === "camera" || source === "screen",
          );
          void captureVisualContext(sources.length > 0 ? sources : ["camera"]).then(({ images, error }) => {
            send({
              type: "capture-context-result",
              requestId,
              prompt,
              images,
              error,
            });
          });
          return;
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
    if (hasSentPageOpenedRef.current) {
      return;
    }
    hasSentPageOpenedRef.current = true;
    send({ type: "page-opened" });
  }, [send]);

  // ── Locale sync ──
  useEffect(() => {
    send({ type: "set-locale", locale });
  }, [locale, send]);

  // ── Character sync ──
  useEffect(() => {
    if (selectedCharacterId) {
      send({ type: "set-character", characterId: selectedCharacterId });
    }
  }, [selectedCharacterId, send]);

  // ── VAD → WS bridge ──
  const handleSpeechEnd = useCallback(
    (audio: Float32Array) => {
      if (micMuted) return;
      const samples = Array.from(audio);
      const CHUNK_SIZE = 4096;
      for (let i = 0; i < samples.length; i += CHUNK_SIZE) {
        send({ type: "mic-audio-data", audio: samples.slice(i, i + CHUNK_SIZE) });
      }
      send({ type: "mic-audio-end", images: [] });
    },
    [send, micMuted],
  );

  useVAD({
    onSpeechEnd: handleSpeechEnd,
    enabled: micGranted && !micMuted,
  });

  // ── Periodic camera snapshot for emotion recognition ──
  const snapshotEnabled = cameraGranted;
  useSnapshot({
    intervalMs: snapshotInterval * 1000,
    cameraEnabled: cameraGranted,
    screenEnabled: false,
    cameraStream,
    screenStream: null,
    active: snapshotEnabled,
    onCapture: (images) => {
      send({ type: "periodic-screenshot", images });
    },
  });

  useEffect(() => {
    setSnapshotActive(snapshotEnabled);
  }, [setSnapshotActive, snapshotEnabled]);

  const sendValue = useMemo(() => send, [send]);

  return (
    <SendContext.Provider value={sendValue}>
      <CompanionLayout />
    </SendContext.Provider>
  );
}

export default function App() {
  const { t } = useI18n();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const hydrate = useAuthStore((s) => s.hydrate);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const [ready, setReady] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return !window.localStorage.getItem("sb_token");
  });

  useEffect(() => {
    hydrate();
    const stored = useAuthStore.getState().token;
    if (stored) {
      fetchMe().finally(() => setReady(true));
    }
  }, [fetchMe, hydrate]);

  useEffect(() => {
    if (token && user && user.balance === undefined) {
      fetchMe();
    }
  }, [fetchMe, token, user]);

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <p className="text-slate-500">{t("app.loading")}</p>
      </div>
    );
  }

  if (!token || !user) {
    return <LoginPage />;
  }

  return <AuthenticatedApp />;
}
