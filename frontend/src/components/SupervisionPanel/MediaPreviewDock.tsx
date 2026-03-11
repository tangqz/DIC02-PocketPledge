import { useEffect, useRef } from "react";
import { useI18n } from "@/lib/i18n";
import { useMediaStore } from "@/stores/mediaStore";

export default function MediaPreviewDock({ className = "" }: { className?: string }) {
  const { t } = useI18n();
  const cameraStream = useMediaStore((s) => s.cameraStream);
  const screenStream = useMediaStore((s) => s.screenStream);

  return (
    <section className={`rounded-2xl bg-slate-950/58 p-1.5 shadow-[0_12px_30px_rgba(15,23,42,0.18)] backdrop-blur-md ${className}`.trim()}>
      <div className="flex gap-1.5">
        <PreviewTile label={t("media.camera")} stream={cameraStream} emptyText={t("media.cameraUnavailable")} />
        <PreviewTile label={t("media.screen")} stream={screenStream} emptyText={t("media.screenUnavailable")} />
      </div>
    </section>
  );
}

function PreviewTile({
  label,
  stream,
  emptyText,
}: {
  label: string;
  stream: MediaStream | null;
  emptyText: string;
}) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!videoRef.current) {
      return;
    }
    videoRef.current.srcObject = stream ?? null;
  }, [stream]);

  return (
    <div className="w-[104px] overflow-hidden rounded-xl border border-white/10 bg-slate-900/88 sm:w-[116px]">
      <div className="flex items-center justify-between px-2 py-1">
        <span className="text-[10px] font-medium text-slate-100">{label}</span>
        <span className={`text-[9px] ${stream ? "text-success" : "text-slate-400"}`}>
          {stream ? t("media.ready") : t("media.offline")}
        </span>
      </div>
      <div className="relative aspect-video bg-slate-950">
        {stream ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-2 text-center text-[10px] text-slate-400">
            {emptyText}
          </div>
        )}
      </div>
    </div>
  );
}