/* ────────────────────────────────────────────────
 *  CameraPreview  –  Shown in Setup for environment calibration
 * ──────────────────────────────────────────────── */
import { useEffect, useRef, useState } from "react";
import { useMediaStore } from "@/stores/mediaStore";

export default function CameraPreview() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const cameraStream = useMediaStore((s) => s.cameraStream);
  const requestCamera = useMediaStore((s) => s.requestCamera);

  useEffect(() => {
    if (cameraStream) {
      setError(null);
      if (videoRef.current) {
        videoRef.current.srcObject = cameraStream;
      }
      return;
    }

    requestCamera().then((granted) => {
      if (!granted) {
        setError("无法访问摄像头，请检查权限设置");
      }
    });
  }, [cameraStream, requestCamera]);

  useEffect(() => {
    if (!videoRef.current) {
      return;
    }
    videoRef.current.srcObject = cameraStream;
  }, [cameraStream]);

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
