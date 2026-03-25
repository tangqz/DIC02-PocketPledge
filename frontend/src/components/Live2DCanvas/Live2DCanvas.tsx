/* ────────────────────────────────────────────────
 *  Live2DCanvas  –  Renders the Live2D model on a <canvas>
 *
 *  Uses Open-LLM-VTuber WebSDK rendering pipeline and keeps
 *  the same imperative API for expression + audio control.
 * ──────────────────────────────────────────────── */

import {
  useRef,
  useImperativeHandle,
  forwardRef,
  useEffect,
  useState,
  useMemo,
  useCallback,
} from "react";
import { DEFAULT_MODEL_CONFIG, type ModelConfig } from "@/lib/modelConfig";
import { useI18n } from "@/lib/i18n";
import { useAudioQueue } from "@/components/AudioPlayer/useAudioQueue";
import { useAvatarStore } from "@/stores/avatarStore";
import { useSessionStore } from "@/stores/sessionStore";
import { updateInteractionConfig, updateModelConfig, setOnModelTapped } from "@/live2d/WebSDK/src/lappdefine";

const IS_DEV = import.meta.env.DEV;

/** Imperative API exposed to parent via ref */
export interface Live2DCanvasHandle {
  setExpression: (emotionKeyword: string) => void;
  playAudio: (base64Wav: string) => Promise<void>;
  stopAudio: () => void;
}

export interface Live2DCanvasProps {
  onModelTapped?: (hitArea: string) => void;
}

const Live2DCanvas = forwardRef<Live2DCanvasHandle, Live2DCanvasProps>(({ onModelTapped }, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const lipSyncRafRef = useRef<number | null>(null);
  const sdkRef = useRef<{
    initializeLive2D?: () => void;
    LAppAdapter?: {
      getInstance: () => {
        getModel: () => {
          _modelSetting?: unknown;
        } | null;
        getExpressionCount: () => number;
        getMotionGroups: () => string[];
        getExpressionName: (index: number) => string;
        setExpression: (name: string) => void;
        setExternalLipSyncValue: (value: number) => void;
        getMotionCount: (group: string) => number;
        startMotion: (group: string, no: number, priority: number) => number;
        setChara: (resourceRoot: string, modelDir: string) => void;
      };
    };
    LAppDelegate?: {
      releaseInstance: () => void;
    };
  } | null>(null);
  const modelInfo = useAvatarStore((s) => s.modelInfo);
  const currentExpression = useAvatarStore((s) => s.currentExpression);
  const pendingAudioMessages = useAvatarStore((s) => s.pendingAudioMessages);
  const playbackInterruptVersion = useAvatarStore((s) => s.playbackInterruptVersion);
  const shiftAudioMessage = useAvatarStore((s) => s.shiftAudioMessage);
  const degradedMode = useSessionStore((s) => s.degradedMode);
  const config = useMemo(
    () =>
      modelInfo
        ? {
            ...DEFAULT_MODEL_CONFIG,
            ...modelInfo,
            emotionMap: {
              ...DEFAULT_MODEL_CONFIG.emotionMap,
              ...modelInfo.emotionMap,
            },
          }
        : DEFAULT_MODEL_CONFIG,
    [modelInfo],
  );
  const { t } = useI18n();

  const [debugText, setDebugText] = useState("init");
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastGoodConfig, setLastGoodConfig] = useState<ModelConfig | null>(null);
  const [fallbackToDefault, setFallbackToDefault] = useState(false);

  const activeConfig = useMemo(() => {
    if (!fallbackToDefault || !lastGoodConfig) {
      return config;
    }
    return lastGoodConfig;
  }, [config, fallbackToDefault, lastGoodConfig]);

  useEffect(() => {
    setFallbackToDefault(false);
  }, [config.url]);

  /* Register the Live2D tap → React callback bridge */
  useEffect(() => {
    setOnModelTapped(onModelTapped ?? null);
    return () => setOnModelTapped(null);
  }, [onModelTapped]);

  const setExpression = useCallback(
    (emotionKeyword: string) => {
      const adapter = sdkRef.current?.LAppAdapter?.getInstance();
      if (!adapter) {
        return;
      }
      const normalizedKeyword = emotionKeyword.toLowerCase();
      const aliasMap: Record<string, string> = {
        anger: "angry",
        joyful: "happy",
        encourage: "encouraging",
      };
      const mappedKeyword = aliasMap[normalizedKeyword] ?? normalizedKeyword;
      const idx = config.emotionMap[mappedKeyword];
      if (idx === undefined) {
        return;
      }
      const expName = adapter.getExpressionName(idx);
      if (expName) {
        adapter.setExpression(expName);
      }
    },
    [config.emotionMap],
  );

  const stopExternalLipSync = useCallback(() => {
    if (lipSyncRafRef.current != null) {
      window.cancelAnimationFrame(lipSyncRafRef.current);
      lipSyncRafRef.current = null;
    }
    const adapter = sdkRef.current?.LAppAdapter?.getInstance();
    adapter?.setExternalLipSyncValue(0);
  }, []);

  const startExternalLipSync = useCallback(
    (audio: HTMLAudioElement) => {
      const adapter = sdkRef.current?.LAppAdapter?.getInstance();
      if (!adapter) {
        return;
      }

      stopExternalLipSync();

      const AudioCtx = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) {
        return;
      }

      try {
        const context = audioContextRef.current ?? new AudioCtx();
        audioContextRef.current = context;
        if (context.state === "suspended") {
          void context.resume();
        }

        const analyser = context.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.55;
        const source = context.createMediaElementSource(audio);
        source.connect(analyser);
        analyser.connect(context.destination);

        const samples = new Uint8Array(analyser.fftSize);
        const gain = Math.max(0.1, Number(activeConfig.lipSyncGain) || 1.0);

        const cleanup = () => {
          stopExternalLipSync();
          source.disconnect();
          analyser.disconnect();
          audio.removeEventListener("ended", cleanup);
          audio.removeEventListener("pause", cleanup);
          audio.removeEventListener("error", cleanup);
        };

        const tick = () => {
          analyser.getByteTimeDomainData(samples);
          let sum = 0;
          for (let i = 0; i < samples.length; i++) {
            const centered = (samples[i] - 128) / 128;
            sum += centered * centered;
          }
          const rms = Math.sqrt(sum / samples.length);
          const mapped = Math.min(1.0, rms * gain * 8.0);
          adapter.setExternalLipSyncValue(mapped);

          if (!audio.paused && !audio.ended) {
            lipSyncRafRef.current = window.requestAnimationFrame(tick);
          }
        };

        audio.addEventListener("ended", cleanup, { once: true });
        audio.addEventListener("pause", cleanup, { once: true });
        audio.addEventListener("error", cleanup, { once: true });
        lipSyncRafRef.current = window.requestAnimationFrame(tick);
      } catch (err) {
        console.warn("[Live2DCanvas] external lip sync init failed", err);
      }
    },
    [activeConfig.lipSyncGain, stopExternalLipSync],
  );

  const stopAudio = useCallback(() => {
    stopExternalLipSync();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      if (audioRef.current.src.startsWith("blob:")) {
        URL.revokeObjectURL(audioRef.current.src);
      }
      audioRef.current = null;
    }
  }, []);

  const parseModelPath = (modelUrl: string) => {
    const trimmed = modelUrl.replace(/^\/+/, "");
    const parts = trimmed.split("/");
    if (parts.length < 3) {
      throw new Error(`Invalid model url: ${modelUrl}`);
    }

    const modelDir = parts[parts.length - 2];
    const modelFileName = parts[parts.length - 1].replace(/\.model3\.json$/i, "");
    const resourceRoot = `/${parts.slice(0, parts.length - 2).join("/")}`;
    return { resourceRoot, modelDir, modelFileName };
  };

  const playBase64Audio = async (base64Wav: string) => {
    const adapter = sdkRef.current?.LAppAdapter?.getInstance();
    const talkGroup = activeConfig.talkMotionGroup ?? "";
    if (adapter) {
      const motionCount = adapter.getMotionCount(talkGroup);
      if (motionCount > 0) {
        const randomIndex = Math.floor(Math.random() * motionCount);
        adapter.startMotion(talkGroup, randomIndex, 2);
      }
    }

    const pureBase64 = base64Wav.includes(",")
      ? base64Wav.split(",")[1]
      : base64Wav;

    const binary = atob(pureBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    const blob = new Blob([bytes], { type: "audio/wav" });
    const url = URL.createObjectURL(blob);

    if (audioRef.current) {
      audioRef.current.pause();
      if (audioRef.current.src.startsWith("blob:")) {
        URL.revokeObjectURL(audioRef.current.src);
      }
      audioRef.current = null;
    }

    const audio = new Audio(url);
    audioRef.current = audio;
    return new Promise<void>((resolve, reject) => {
      const onEnded = () => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        URL.revokeObjectURL(url);
        if (audioRef.current === audio) {
          audioRef.current = null;
        }
        resolve();
      };

      const onError = () => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        URL.revokeObjectURL(url);
        if (audioRef.current === audio) {
          audioRef.current = null;
        }
        reject(new Error("Audio playback error"));
      };

      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);
      startExternalLipSync(audio);

      audio.play().catch((err) => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        stopExternalLipSync();
        URL.revokeObjectURL(url);
        if (audioRef.current === audio) {
          audioRef.current = null;
        }
        reject(err);
      });
    });
  };

  const { enqueue, interrupt } = useAudioQueue({
    setExpression,
    playAudio: playBase64Audio,
    stopAudio,
    onQueueEmpty: () => undefined,
  });

  // Runtime diagnostics overlay
  useEffect(() => {
    if (!IS_DEV) {
      return;
    }

    const timer = setInterval(() => {
      try {
        const adapter = sdkRef.current?.LAppAdapter?.getInstance();
        if (!adapter) {
          setDebugText(`loaded=${isLoaded ? 1 : 0} sdk=0`);
          return;
        }
        const model = adapter.getModel();
        if (!model || !model._modelSetting) {
          setDebugText(`loaded=${isLoaded ? 1 : 0} model=0 ready=0`);
          return;
        }
        const expressionCount = adapter.getExpressionCount();
        const motionGroups = adapter.getMotionGroups();
        setDebugText(
          `loaded=${isLoaded ? 1 : 0} model=${model ? 1 : 0} exp=${expressionCount} motGroups=${motionGroups.length}`,
        );
      } catch (e) {
        setDebugText(`debug-error=${(e as Error).message}`);
      }
    }, 500);

    return () => clearInterval(timer);
  }, [isLoaded]);

  // Expose imperative methods to parent
  useImperativeHandle(
    ref,
    () => ({
      setExpression,
      playAudio: playBase64Audio,
      stopAudio,
    }),
    [playBase64Audio, setExpression, stopAudio],
  );

  useEffect(() => {
    if (!isLoaded || !currentExpression) {
      return;
    }
    setExpression(currentExpression);
  }, [currentExpression, isLoaded, setExpression]);

  useEffect(() => {
    if (pendingAudioMessages.length === 0 || degradedMode) {
      return;
    }
    enqueue(pendingAudioMessages[0]);
    shiftAudioMessage();
  }, [degradedMode, enqueue, pendingAudioMessages, shiftAudioMessage]);

  useEffect(() => {
    if (!degradedMode) {
      return;
    }
    interrupt();
  }, [degradedMode, interrupt]);

  useEffect(() => {
    if (playbackInterruptVersion === 0) {
      return;
    }
    interrupt();
  }, [interrupt, playbackInterruptVersion]);

  useEffect(() => {
    let disposed = false;
    setIsLoaded(false);
    setError(null);

    const init = async () => {
      try {
        if (!(window as Window & { Live2DCubismCore?: unknown }).Live2DCubismCore) {
          throw new Error("Live2D Core 未加载");
        }

        const [{ initializeLive2D }, { LAppAdapter }, { LAppDelegate }] =
          await Promise.all([
            import("@cubismsdksamples/main"),
            import("@cubismsdksamples/lappadapter"),
            import("@cubismsdksamples/lappdelegate"),
          ]);

        sdkRef.current = { initializeLive2D, LAppAdapter, LAppDelegate };

        const { resourceRoot, modelDir, modelFileName } = parseModelPath(activeConfig.url);
        updateModelConfig(resourceRoot, modelDir, modelFileName, Number(activeConfig.kScale) || undefined);
        updateInteractionConfig(activeConfig.tapMotions, activeConfig.emotionMap);
        initializeLive2D();

        if (disposed) {
          LAppDelegate.releaseInstance();
          return;
        }

        // Give runtime a short window to finish async model setup; fallback if MOC is unsupported.
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        const adapter = LAppAdapter?.getInstance?.();
        const model = adapter?.getModel?.();
        const runtimeModel = (model as unknown as { _model?: unknown } | null)?._model;
        if (!runtimeModel) {
          throw new Error("Model runtime not ready (possibly unsupported moc version)");
        }

        if (!disposed) {
          setIsLoaded(true);
          if (!fallbackToDefault) {
            setLastGoodConfig(config);
          }
        }
      } catch (e) {
        if (!disposed) {
          const err = e as Error;
          // Auto-fallback only to last known good config; avoid first-login cross-character flip.
          if (!fallbackToDefault && lastGoodConfig && config.url !== lastGoodConfig.url) {
            console.warn("[Live2DCanvas] model load failed, fallback to last good model", err);
            setFallbackToDefault(true);
            return;
          }
          setError(err);
        }
      }
    };

    init();

    return () => {
      disposed = true;
      try {
        sdkRef.current?.LAppDelegate?.releaseInstance?.();
      } catch (releaseError) {
        console.warn("[Live2DCanvas] releaseInstance failed", releaseError);
      }
      stopAudio();
      stopExternalLipSync();
    };
  }, [activeConfig.url, activeConfig.kScale, config, lastGoodConfig, fallbackToDefault, stopAudio, stopExternalLipSync]);

  return (
    <div id="live2d" className="relative h-full w-full">
      <canvas
        id="canvas"
        ref={canvasRef}
        className="h-full w-full cursor-default"
      />

      {/* Loading overlay */}
      {!isLoaded && !error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-sm text-slate-500">{t("live2d.loading")}</span>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="max-w-xs rounded-xl bg-danger/20 p-4 text-center text-sm text-danger">
            <p className="font-semibold">{t("live2d.error")}</p>
            <p className="mt-1 text-xs opacity-80">{error.message}</p>
          </div>
        </div>
      )}


    </div>
  );
});

Live2DCanvas.displayName = "Live2DCanvas";
export default Live2DCanvas;
