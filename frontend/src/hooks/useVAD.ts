/* ────────────────────────────────────────────────
 *  useVAD  –  Browser voice-activity detection via @ricky0123/vad-web
 *
 *  On speech start → sets isListening=true in mediaStore
 *  On speech end   → fires callback with Float32Array audio data
 *  Automatically paused when agent is speaking.
 * ──────────────────────────────────────────────── */

import { useEffect, useRef, useCallback } from "react";
import { MicVAD } from "@ricky0123/vad-web";
import { useMediaStore } from "@/stores/mediaStore";
import { useChatStore } from "@/stores/chatStore";
import ortWasmThreadedMjsUrl from "@/assets/ort/ort-wasm-simd-threaded.mjs?url";
import ortWasmThreadedWasmUrl from "@/assets/ort/ort-wasm-simd-threaded.wasm?url";

const VAD_ASSET_BASE_PATH = "/vad/";
const ORT_WASM_PATHS = {
  mjs: ortWasmThreadedMjsUrl,
  wasm: ortWasmThreadedWasmUrl,
};

export interface UseVADOptions {
  /** Called with PCM audio (Float32Array, 16kHz mono) when speech segment ends */
  onSpeechEnd: (audio: Float32Array) => void;
  /** Enable VAD on mount? Default true */
  enabled?: boolean;
}

/**
 * Convert Float32Array PCM to base64 WAV (16kHz, 16-bit mono)
 */
export function float32ToBase64Wav(
  samples: Float32Array,
  sampleRate = 16000,
): string {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const dataLength = samples.length * blockAlign;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  // RIFF header
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeString(view, 8, "WAVE");

  // fmt chunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true); // chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);

  // data chunk
  writeString(view, 36, "data");
  view.setUint32(40, dataLength, true);

  // Convert float samples to 16-bit PCM
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  // Convert to base64
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function writeString(view: DataView, offset: number, s: string) {
  for (let i = 0; i < s.length; i++) {
    view.setUint8(offset + i, s.charCodeAt(i));
  }
}

export function useVAD({ onSpeechEnd, enabled = true }: UseVADOptions) {
  const vadRef = useRef<MicVAD | null>(null);
  const { setIsListening, setVadActive, setMicGranted } = useMediaStore.getState();
  const isAgentSpeaking = useChatStore((s) => s.isAgentSpeaking);
  const micMuted = useMediaStore((s) => s.micMuted);
  const onSpeechEndRef = useRef(onSpeechEnd);
  onSpeechEndRef.current = onSpeechEnd;

  // Create VAD instance
  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    async function init() {
      try {
        const vad = await MicVAD.new({
          baseAssetPath: VAD_ASSET_BASE_PATH,
          onnxWASMBasePath: ORT_WASM_PATHS as unknown as string,
          model: "legacy",
          positiveSpeechThreshold: 0.8,
          negativeSpeechThreshold: 0.3,
          preSpeechPadMs: 300,
          redemptionMs: 300,
          onSpeechStart: () => {
            if (!cancelled) setIsListening(true);
          },
          onSpeechEnd: (audio: Float32Array) => {
            if (!cancelled) {
              setIsListening(false);
              onSpeechEndRef.current(audio);
            }
          },
        });

        if (cancelled) {
          vad.destroy();
          return;
        }

        vadRef.current = vad;
        setVadActive(true);
        setMicGranted(true);
        vad.start();
        console.log("[useVAD] Initialized and started");
      } catch (err) {
        console.error("[useVAD] Failed to initialize:", err);
        setVadActive(false);
        // Keep micGranted as-is: permission status should not be rolled back
        // just because VAD runtime initialization fails.
      }
    }

    init();

    return () => {
      cancelled = true;
      if (vadRef.current) {
        void vadRef.current.destroy();
        vadRef.current = null;
      }
      setVadActive(false);
      setIsListening(false);
    };
  }, [enabled]);

  // Pause/resume when agent is speaking or user mutes mic
  useEffect(() => {
    const vad = vadRef.current;
    if (!vad) return;

    if (isAgentSpeaking || micMuted) {
      vad.pause();
    } else {
      vad.start();
    }
  }, [isAgentSpeaking, micMuted]);

  const destroy = useCallback(() => {
    if (vadRef.current) {
      void vadRef.current.destroy();
      vadRef.current = null;
      setVadActive(false);
    }
  }, []);

  return { destroy };
}
