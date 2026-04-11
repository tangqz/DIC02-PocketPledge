import { useEffect, useRef } from "react";

import { useI18n } from "@/lib/i18n";
import { useMediaStore } from "@/stores/mediaStore";

interface CameraPreviewDockProps {
  className?: string;
}

export default function CameraPreviewDock({ className = "" }: CameraPreviewDockProps) {
  const { locale, t } = useI18n();
  const cameraStream = useMediaStore((s) => s.cameraStream);
  const cameraGranted = useMediaStore((s) => s.cameraGranted);
  const snapshotInterval = useMediaStore((s) => s.snapshotInterval);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!videoRef.current) {
      return;
    }
    videoRef.current.srcObject = cameraStream ?? null;
  }, [cameraStream]);

  return (
    <section
      className={`w-44 overflow-hidden rounded-2xl border border-white/20 bg-slate-950/65 p-1.5 shadow-lg backdrop-blur-md ${className}`.trim()}
    >
      <div className="mb-1 flex items-center justify-between px-1 text-[10px] text-slate-200">
        <span>{t("media.camera")}</span>
        <span className={cameraGranted ? "text-emerald-300" : "text-slate-400"}>
          {cameraGranted ? t("media.ready") : t("media.offline")}
        </span>
      </div>

      <div className="relative aspect-video overflow-hidden rounded-xl bg-slate-900">
        {cameraStream ? (
          <video ref={videoRef} autoPlay playsInline muted className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center px-2 text-center text-[10px] text-slate-400">
            {t("media.cameraUnavailable")}
          </div>
        )}
      </div>

      <p className="mt-1 px-1 text-[10px] text-slate-400">
        {locale === "zh"
          ? `情绪检测频率：每 ${snapshotInterval} 秒`
          : `Emotion detection interval: ${snapshotInterval}s`}
      </p>
    </section>
  );
}
