/* ────────────────────────────────────────────────
 *  useSnapshot  –  Periodic screenshot + camera capture
 *
 *  Captures from camera (getUserMedia) and/or screen (getDisplayMedia).
 *  Returns base64 JPEG images at a configurable interval.
 * ──────────────────────────────────────────────── */

import { useEffect, useRef, useCallback, useState } from "react";
import type { SnapshotImage } from "@/lib/protocol";

async function ensureVideoReady(
  video: HTMLVideoElement,
  timeoutMs = 1500,
): Promise<boolean> {
  if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0 && video.videoHeight > 0) {
    return true;
  }

  return await new Promise<boolean>((resolve) => {
    let settled = false;
    const finish = (result: boolean) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      video.removeEventListener("loadeddata", handleReady);
      video.removeEventListener("canplay", handleReady);
      resolve(result);
    };
    const handleReady = () => finish(true);
    const timer = window.setTimeout(() => finish(false), timeoutMs);

    video.addEventListener("loadeddata", handleReady, { once: true });
    video.addEventListener("canplay", handleReady, { once: true });
    void video.play().catch(() => undefined);
  });
}

function captureFrameFromStream(
  stream: MediaStream,
  canvas: HTMLCanvasElement,
  videoCache: Map<string, HTMLVideoElement>,
): string | null {
  const track = stream.getVideoTracks()[0];
  if (!track || track.readyState !== "live") return null;

  const settings = track.getSettings();
  const width = settings.width || 640;
  const height = settings.height || 480;
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const streamKey = track.id;
  const video = getOrCreateVideoElement(stream, streamKey, videoCache);

  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    return null;
  }

  try {
    ctx.drawImage(video, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.7).split(",")[1];
  } catch {
    return null;
  }
}

function getOrCreateVideoElement(
  stream: MediaStream,
  streamKey: string,
  videoCache: Map<string, HTMLVideoElement>,
): HTMLVideoElement {
  let video = videoCache.get(streamKey);
  if (!video) {
    video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.play().catch(() => undefined);
    videoCache.set(streamKey, video);
  }
  return video;
}


async function captureFrameFromStreamWithWait(
  stream: MediaStream,
  canvas: HTMLCanvasElement,
  videoCache: Map<string, HTMLVideoElement>,
): Promise<string | null> {
  const track = stream.getVideoTracks()[0];
  if (!track || track.readyState !== "live") return null;

  const video = getOrCreateVideoElement(stream, track.id, videoCache);
  await ensureVideoReady(video);
  return captureFrameFromStream(stream, canvas, videoCache);
}

export async function captureImagesFromStreams(options: {
  cameraEnabled?: boolean;
  screenEnabled?: boolean;
  cameraStream?: MediaStream | null;
  screenStream?: MediaStream | null;
}): Promise<SnapshotImage[]> {
  const canvas = document.createElement("canvas");
  const videoCache = new Map<string, HTMLVideoElement>();
  const images: SnapshotImage[] = [];

  try {
    if (options.cameraEnabled && options.cameraStream) {
      const cameraTrack = options.cameraStream.getVideoTracks()[0];
      const cameraSettings = cameraTrack?.getSettings?.() ?? {};
      const data = await captureFrameFromStreamWithWait(options.cameraStream, canvas, videoCache);
      if (data) {
        images.push({
          source: "camera",
          data,
          mime_type: "image/jpeg",
          metadata: {
            width: Number(cameraSettings.width) || undefined,
            height: Number(cameraSettings.height) || undefined,
            facingMode: typeof cameraSettings.facingMode === "string" ? cameraSettings.facingMode : undefined,
          },
        });
      }
    }

    if (options.screenEnabled && options.screenStream) {
      const screenTrack = options.screenStream.getVideoTracks()[0];
      const screenSettings = screenTrack?.getSettings?.() ?? {};
      const data = await captureFrameFromStreamWithWait(options.screenStream, canvas, videoCache);
      if (data) {
        images.push({
          source: "screen",
          data,
          mime_type: "image/jpeg",
          metadata: {
            width: Number(screenSettings.width) || undefined,
            height: Number(screenSettings.height) || undefined,
            displaySurface: typeof screenSettings.displaySurface === "string" ? screenSettings.displaySurface : undefined,
          },
        });
      }
    }
  } finally {
    videoCache.forEach((video) => {
      video.pause();
      video.srcObject = null;
    });
    videoCache.clear();
  }

  return images;
}

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
  /** Optional shared camera stream from store */
  cameraStream?: MediaStream | null;
  /** Optional shared screen stream from store */
  screenStream?: MediaStream | null;
}

export function useSnapshot({
  intervalMs = 15_000,
  cameraEnabled = true,
  screenEnabled = false,
  onCapture,
  active = false,
  cameraStream,
  screenStream,
}: UseSnapshotOptions) {
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const videoCacheRef = useRef<Map<string, HTMLVideoElement>>(new Map());
  const onCaptureRef = useRef(onCapture);
  onCaptureRef.current = onCapture;
  const [cameraReady, setCameraReady] = useState(false);
  const [screenReady, setScreenReady] = useState(false);

  useEffect(() => {
    cameraStreamRef.current = cameraStream ?? null;
    setCameraReady(Boolean(cameraStream));
  }, [cameraStream]);

  useEffect(() => {
    screenStreamRef.current = screenStream ?? null;
    setScreenReady(Boolean(screenStream));
  }, [screenStream]);

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
      return captureFrameFromStream(stream, canvas, videoCacheRef.current);
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
      videoCacheRef.current.forEach((video) => {
        video.pause();
        video.srcObject = null;
      });
      videoCacheRef.current.clear();
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
