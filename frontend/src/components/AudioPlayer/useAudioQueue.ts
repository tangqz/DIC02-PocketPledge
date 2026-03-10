/* ────────────────────────────────────────────────
 *  useAudioQueue  –  FIFO playback queue
 *
 *  Each task: set expression → start talk motion → play audio (lip sync)
 *  → display subtitle → on end → next task → when empty → notify complete
 * ──────────────────────────────────────────────── */

import { useRef, useCallback, useEffect } from "react";
import { useChatStore } from "@/stores/chatStore";
import type { AudioMessage } from "@/lib/protocol";

export interface AudioTask {
  audio: string; // base64 WAV
  expressions: string[];
  displayText: string;
  displayName: string;
}

interface Callbacks {
  setExpression: (keyword: string) => void;
  playAudio: (base64: string) => Promise<void>;
  stopAudio: () => void;
  onQueueEmpty: () => void;
}

export function useAudioQueue(callbacks: Callbacks) {
  const queueRef = useRef<AudioTask[]>([]);
  const processingRef = useRef(false);
  const { setAgentSpeaking } = useChatStore.getState();

  const processNext = useCallback(async () => {
    if (processingRef.current) return;
    if (queueRef.current.length === 0) {
      setAgentSpeaking(false);
      callbacks.onQueueEmpty();
      return;
    }

    processingRef.current = true;
    const task = queueRef.current.shift()!;

    // 1. Set expression
    if (task.expressions.length > 0) {
      callbacks.setExpression(task.expressions[0]);
    }

    setAgentSpeaking(true);

    // 3. Play audio with lip sync (blocks until done)
    try {
      await callbacks.playAudio(task.audio);
    } catch (error) {
      callbacks.stopAudio();
      console.error("Audio playback failed in useAudioQueue:", error);
    } finally {
      processingRef.current = false;
      processNext();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callbacks]);

  /** Enqueue an audio message from the backend */
  const enqueue = useCallback(
    (msg: AudioMessage) => {
      const task: AudioTask = {
        audio: msg.audio,
        expressions: msg.actions.expressions,
        displayText: msg.display_text.text,
        displayName: msg.display_text.name,
      };
      queueRef.current.push(task);

      // Kick off processing if idle
      if (!processingRef.current) {
        processNext();
      }
    },
    [processNext],
  );

  /** Clear queue and stop current playback (for interrupts) */
  const interrupt = useCallback(() => {
    queueRef.current = [];
    processingRef.current = false;
    callbacks.stopAudio();
    setAgentSpeaking(false);
  }, [callbacks]);

  /** Current queue length */
  const queueLength = () => queueRef.current.length;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      queueRef.current = [];
      processingRef.current = false;
    };
  }, []);

  return { enqueue, interrupt, queueLength };
}
