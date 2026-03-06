/* ────────────────────────────────────────────────
 *  useSnapshot  –  Periodic screenshot + camera capture
 *
 *  Captures from camera (getUserMedia) and/or screen (getDisplayMedia).
 *  Returns base64 JPEG images at a configurable interval.
 * ──────────────────────────────────────────────── */

import { useEffect, useRef, useCallback, useState } from "react";
import type { SnapshotImage } from "@/lib/protocol";

export interface UseSnapshotOptions {
  /** Interval in milliseconds between captures */
  intervalMs?: number;
  /** Enable camera capture */
  cameraEnabled?: boolean;
  /** Enable screen capture */
  screenEnabled?: boolean;
  /** Callback when new snapshots are ready */
  onCapture: (images: SnapshotImage[]) => void;
  /** Whether snapshot loop is active */
  active?: boolean;
}

export function useSnapshot({
  intervalMs = 15_000,
  cameraEnabled = true,
  screenEnabled = false,
  onCapture,
  active = false,
}: UseSnapshotOptions) {
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const onCaptureRef = useRef(onCapture);
  onCaptureRef.current = onCapture;
  const [cameraReady, setCameraReady] = useState(false);
  const [screenReady, setScreenReady] = useState(false);

  // Create an offscreen canvas for capturing
  useEffect(() => {
    canvasRef.current = document.createElement("canvas");
    return () => {
      canvasRef.current = null;
    };
  }, []);

  // Request camera
  const requestCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
        audio: false,
      });
      cameraStreamRef.current = stream;
      setCameraReady(true);
      return true;
    } catch (err) {
      console.warn("[Snapshot] Camera access denied:", err);
      setCameraReady(false);
      return false;
    }
  }, []);

  // Request screen share
  const requestScreen = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { width: 1280, height: 720 },
      });
      screenStreamRef.current = stream;
      setScreenReady(true);

      // Handle user stopping screen share
      stream.getVideoTracks()[0].onended = () => {
        screenStreamRef.current = null;
        setScreenReady(false);
      };
      return true;
    } catch (err) {
      console.warn("[Snapshot] Screen share denied:", err);
      setScreenReady(false);
      return false;
    }
  }, []);

  /** Capture a frame from a MediaStream → base64 JPEG */
  const captureFrame = useCallback(
    (stream: MediaStream): string | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;

      const track = stream.getVideoTracks()[0];
      if (!track || track.readyState !== "live") return null;

      const settings = track.getSettings();
      const w = settings.width || 640;
      const h = settings.height || 480;
      canvas.width = w;
      canvas.height = h;

      // Use ImageCapture API if available, otherwise fallback to video element
      const ctx = canvas.getContext("2d");
      if (!ctx) return null;

      // Create a temporary video element
      const video = document.createElement("video");
      video.srcObject = stream;
      video.muted = true;
      video.playsInline = true;

      // This is synchronous if video is already playing
      try {
        ctx.drawImage(video, 0, 0, w, h);
        return canvas.toDataURL("image/jpeg", 0.7).split(",")[1];
      } catch {
        return null;
      }
    },
    [],
  );

  // Periodic capture loop
  useEffect(() => {
    if (!active) return;

    const timer = setInterval(() => {
      const images: SnapshotImage[] = [];

      if (cameraEnabled && cameraStreamRef.current) {
        const data = captureFrame(cameraStreamRef.current);
        if (data) {
          images.push({
            source: "camera" as const,
            data,
            mime_type: "image/jpeg",
          });
        }
      }

      if (screenEnabled && screenStreamRef.current) {
        const data = captureFrame(screenStreamRef.current);
        if (data) {
          images.push({
            source: "screen" as const,
            data,
            mime_type: "image/jpeg",
          });
        }
      }

      if (images.length > 0) {
        onCaptureRef.current(images);
      }
    }, intervalMs);

    return () => clearInterval(timer);
  }, [active, cameraEnabled, screenEnabled, intervalMs, captureFrame]);

  // Cleanup streams on unmount
  useEffect(() => {
    return () => {
      cameraStreamRef.current?.getTracks().forEach((t) => t.stop());
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return {
    requestCamera,
    requestScreen,
    cameraReady,
    screenReady,
    cameraStream: cameraStreamRef.current,
  };
}
