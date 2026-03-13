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

  const streamKey = track.id;
  const video = getOrCreateVideoElement(stream, streamKey, videoCache);
  const settings = track.getSettings();
  // Prefer actual decoded frame size over track settings to avoid browser-reported low fallback values.
  const width = video.videoWidth || settings.width || 1280;
  const height = video.videoHeight || settings.height || 720;
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    return null;
  }

  try {
    ctx.drawImage(video, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.9).split(",")[1];
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
        const trackSettings = options.cameraStream.getVideoTracks()[0]?.getSettings?.() ?? {};
        images.push({
          source: "camera",
          data,
          mime_type: "image/jpeg",
          metadata: {
            width: Number(trackSettings.width || cameraSettings.width) || undefined,
            height: Number(trackSettings.height || cameraSettings.height) || undefined,
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
        const trackSettings = options.screenStream.getVideoTracks()[0]?.getSettings?.() ?? {};
        images.push({
          source: "screen",
          data,
          mime_type: "image/jpeg",
          metadata: {
            width: Number(trackSettings.width || screenSettings.width) || undefined,
            height: Number(trackSettings.height || screenSettings.height) || undefined,
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
  const [cameraReadyInternal, setCameraReady] = useState(false);

  useEffect(() => {
    onCaptureRef.current = onCapture;
  }, [onCapture]);
  const [screenReadyInternal, setScreenReady] = useState(false);

  const cameraReady = cameraReadyInternal || Boolean(cameraStream);
  const screenReady = screenReadyInternal || Boolean(screenStream);

  useEffect(() => {
    cameraStreamRef.current = cameraStream ?? null;
  }, [cameraStream]);

  useEffect(() => {
    screenStreamRef.current = screenStream ?? null;
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
        video: {
          facingMode: "user",
          width: { ideal: 1920, min: 1280 },
          height: { ideal: 1080, min: 720 },
        },
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
        video: {
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 15, max: 30 },
        },
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
    (stream: MediaStream): { data: string; width?: number; height?: number } | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const data = captureFrameFromStream(stream, canvas, videoCacheRef.current);
      if (!data) return null;
      const settings = stream.getVideoTracks()[0]?.getSettings?.() ?? {};
      return {
        data,
        width: Number(settings.width) || undefined,
        height: Number(settings.height) || undefined,
      };
    },
    [],
  );

  const historyBufferRef = useRef<{ timestamp: number; images: SnapshotImage[] }[]>([]);

  // Periodic capture loop
  useEffect(() => {
    if (!active) {
      historyBufferRef.current = [];
      return;
    }

    const captureInterval = setInterval(() => {
      const images: SnapshotImage[] = [];
      const timestamp = Date.now();

      if (cameraEnabled && cameraStreamRef.current) {
        const captured = captureFrame(cameraStreamRef.current);
        if (captured?.data) {
          images.push({
            source: "camera" as const,
            data: captured.data,
            mime_type: "image/jpeg",
            metadata: { timestamp, width: captured.width, height: captured.height },
          });
        }
      }

      if (screenEnabled && screenStreamRef.current) {
        const captured = captureFrame(screenStreamRef.current);
        if (captured?.data) {
          images.push({
            source: "screen" as const,
            data: captured.data,
            mime_type: "image/jpeg",
            metadata: { timestamp, width: captured.width, height: captured.height },
          });
        }
      }

      if (images.length > 0) {
        historyBufferRef.current.push({ timestamp, images });

        // Maintain up to a maximum of 10.5 minutes (630 seconds) to cover the 600s maximum target offset
        const maxAgeMs = 630 * 1000;
        const cutoff = timestamp - maxAgeMs;
        historyBufferRef.current = historyBufferRef.current.filter((item) => item.timestamp >= cutoff);
      }
    }, 1000); // Capture frequently (e.g., every 1 second)

    const sendInterval = setInterval(() => {
      if (historyBufferRef.current.length === 0) return;

      const now = Date.now();

      // Nonlinear sparse sampling in seconds (e.g. 1s ago, 5s ago, 15s ago, 30s ago, 60s ago, 120s ago, 300s ago, 600s ago)
      const targetOffsetsSec = [1, 5, 15, 30, 60, 120, 300, 600];
      const targetsMs = targetOffsetsSec.map((s) => s * 1000);

      const selectedImages: SnapshotImage[] = [];
      const seenIds = new Set<number>();

      // We clone the buffer so it won't be modified while iterating
      const buffer = [...historyBufferRef.current];

      for (const tOffsetMs of targetsMs) {
        const targetTime = now - tOffsetMs;

        // Find closest item
        let closestItem = buffer[0];
        let minDiff = Math.abs(buffer[0].timestamp - targetTime);

        for (const item of buffer) {
          const diff = Math.abs(item.timestamp - targetTime);
          if (diff < minDiff) {
            minDiff = diff;
            closestItem = item;
          }
        }

        // Avoid including images that are too far from the target (e.g. gap > 5 seconds)
        // Since we capture every 1s, the gap should be very small (e.g. <= 2 seconds) unless the tab was throttled.
        if (minDiff > 5000) {
          continue;
        }

        // Only include if not chosen before, up to 8 targets (16 images total if camera + screen)
        if (!seenIds.has(closestItem.timestamp) && selectedImages.length < 16) {
          seenIds.add(closestItem.timestamp);
          selectedImages.push(...closestItem.images);
        }
      }

      if (selectedImages.length > 0) {
        onCaptureRef.current(selectedImages);
      }
    }, intervalMs);

    return () => {
      clearInterval(captureInterval);
      clearInterval(sendInterval);
    };
  }, [active, cameraEnabled, screenEnabled, intervalMs, captureFrame]);

  // Cleanup streams on unmount
  useEffect(() => {
    const videoCache = videoCacheRef.current;
    return () => {
      videoCache.forEach((video) => {
        video.pause();
        video.srcObject = null;
      });
      videoCache.clear();
    };
  }, []);

  return {
    requestCamera,
    requestScreen,
    cameraReady,
    screenReady,
    cameraStream,
  };
}
