/* ────────────────────────────────────────────────
 *  CameraPreview  –  Shown in Setup for environment calibration
 * ──────────────────────────────────────────────── */
import { useEffect, useRef, useState } from "react";
import { useMediaStore } from "@/stores/mediaStore";

export default function CameraPreview() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const setCameraGranted = useMediaStore((s) => s.setCameraGranted);

  useEffect(() => {
    let stream: MediaStream | null = null;

    const init = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: 640, height: 480 },
          audio: false,
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraGranted(true);
      } catch (err) {
        setError("无法访问摄像头，请检查权限设置");
        setCameraGranted(false);
        console.warn("[CameraPreview]", err);
      }
    };

    init();

    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [setCameraGranted]);

  if (error) {
    return (
      <div className="flex h-48 items-center justify-center bg-surface text-sm text-white/40">
        {error}
      </div>
    );
  }

  return (
    <video
      ref={videoRef}
      autoPlay
      playsInline
      muted
      className="h-48 w-full object-cover"
    />
  );
}
