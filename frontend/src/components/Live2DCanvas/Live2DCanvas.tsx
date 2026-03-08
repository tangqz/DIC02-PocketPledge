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
} from "react";
import { DEFAULT_MODEL_CONFIG } from "@/lib/modelConfig";
import { useI18n } from "@/lib/i18n";

const IS_DEV = import.meta.env.DEV;

/** Imperative API exposed to parent via ref */
export interface Live2DCanvasHandle {
  setExpression: (emotionKeyword: string) => void;
  playAudio: (base64Wav: string) => Promise<void>;
  stopAudio: () => void;
}

const Live2DCanvas = forwardRef<Live2DCanvasHandle>((_props, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sdkRef = useRef<{
    initializeLive2D?: () => void;
    LAppAdapter?: {
      getInstance: () => {
        getModel: () => unknown;
        getExpressionCount: () => number;
        getMotionGroups: () => string[];
        getExpressionName: (index: number) => string;
        setExpression: (name: string) => void;
        setChara: (resourceRoot: string, modelDir: string) => void;
      };
    };
    LAppDelegate?: {
      releaseInstance: () => void;
    };
  } | null>(null);
  const config = DEFAULT_MODEL_CONFIG;
  const { t } = useI18n();

  const [debugText, setDebugText] = useState("init");
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const parseModelPath = (modelUrl: string) => {
    const trimmed = modelUrl.replace(/^\/+/, "");
    const parts = trimmed.split("/");
    if (parts.length < 3) {
      throw new Error(`Invalid model url: ${modelUrl}`);
    }

    const modelDir = parts[parts.length - 2];
    const resourceRoot = `/${parts.slice(0, parts.length - 2).join("/")}`;
    return { resourceRoot, modelDir };
  };

  const playBase64Audio = async (base64Wav: string) => {
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

      audio.play().catch((err) => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        URL.revokeObjectURL(url);
        if (audioRef.current === audio) {
          audioRef.current = null;
        }
        reject(err);
      });
    });
  };

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
      setExpression: (emotionKeyword: string) => {
        const adapter = sdkRef.current?.LAppAdapter?.getInstance();
        if (!adapter) {
          return;
        }
        const idx = config.emotionMap[emotionKeyword.toLowerCase()];
        if (idx === undefined) {
          return;
        }
        const expName = adapter.getExpressionName(idx);
        if (expName) {
          adapter.setExpression(expName);
        }
      },
      playAudio: playBase64Audio,
      stopAudio: () => {
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current.currentTime = 0;
          if (audioRef.current.src.startsWith("blob:")) {
            URL.revokeObjectURL(audioRef.current.src);
          }
          audioRef.current = null;
        }
      },
    }),
    [config.emotionMap],
  );

  useEffect(() => {
    let disposed = false;

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

        initializeLive2D();
        const adapter = LAppAdapter.getInstance();
        const { resourceRoot, modelDir } = parseModelPath(config.url);
        adapter.setChara(resourceRoot, modelDir);

        if (!disposed) {
          setIsLoaded(true);
        }
      } catch (e) {
        if (!disposed) {
          setError(e as Error);
        }
      }
    };

    init();

    return () => {
      disposed = true;
      sdkRef.current?.LAppDelegate?.releaseInstance?.();
      if (audioRef.current) {
        audioRef.current.pause();
        if (audioRef.current.src.startsWith("blob:")) {
          URL.revokeObjectURL(audioRef.current.src);
        }
        audioRef.current = null;
      }
    };
  }, [config.url]);

  return (
    <div id="live2d" className="relative h-full w-full">
      <canvas
        id="canvas"
        ref={canvasRef}
        className="h-full w-full cursor-pointer"
      />

      {/* Loading overlay */}
      {!isLoaded && !error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-sm text-white/50">{t("live2d.loading")}</span>
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

      {/* Debug overlay (dev only) */}
      {IS_DEV && (
        <div className="pointer-events-none absolute right-2 top-2 rounded bg-black/55 px-2 py-1 font-mono text-[10px] leading-tight text-white/80">
          {debugText}
        </div>
      )}
    </div>
  );
});

Live2DCanvas.displayName = "Live2DCanvas";
export default Live2DCanvas;
