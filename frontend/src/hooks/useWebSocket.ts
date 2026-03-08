/* ────────────────────────────────────────────────
 *  useWebSocket  –  Persistent WebSocket connection to backend
 *
 *  Handles: reconnection, JSON serialization, message dispatch,
 *  connection state tracking.
 *
 *  Dispatch strategy:
 *  ┌──────────────────────────┬────────────────────────────────┐
 *  │ Message type             │ Routed to                      │
 *  ├──────────────────────────┼────────────────────────────────┤
 *  │ agent-text-chunk         │ chatStore.appendStreamingText  │
 *  │ agent-text-end           │ chatStore.commitStreamingText  │
 *  │ supervision-state-change │ sessionStore.applyStateChange  │
 *  │ balance-update           │ sessionStore.applyBalanceUpdate│
 *  │ plan-update              │ sessionStore.applyPlanUpdate   │
 *  │ timer-sync               │ sessionStore.applyTimerSync    │
 *  │ supervision-alert        │ sessionStore.applyAlert        │
 *  │ tool-call-status         │ sessionStore.setActiveToolCall │
 *  │ audio, model-info, ctrl  │ onMessage callback (Live2D etc)│
 *  └──────────────────────────┴────────────────────────────────┘
 * ──────────────────────────────────────────────── */

import { useEffect, useRef, useCallback } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import type { TxMessage, RxMessage } from "@/lib/protocol";

export interface UseWebSocketOptions {
  /** WebSocket URL (default: ws://localhost:12393/ws) */
  url?: string;
  /** Called when an RxMessage is received (for audio/model-info/control) */
  onMessage?: (msg: RxMessage) => void;
  /** Auto-connect on mount? */
  autoConnect?: boolean;
}

const DEFAULT_URL = "ws://localhost:12393/ws";
const RECONNECT_DELAY = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

export function useWebSocket({
  url = DEFAULT_URL,
  onMessage,
  autoConnect = true,
}: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const { setIsConnected } = useSessionStore.getState();

  const connect = useCallback(() => {
    // Don't double-connect
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected to", url);
      setIsConnected(true);
      reconnectCountRef.current = 0;
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected");
      setIsConnected(false);
      wsRef.current = null;

      // Auto-reconnect
      if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectCountRef.current++;
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY);
      }
    };

    ws.onerror = (err) => {
      console.error("[WS] Error:", err);
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as RxMessage;
        dispatch(msg);
        onMessageRef.current?.(msg);
      } catch (err) {
        console.warn("[WS] Invalid message:", err);
      }
    };
  }, [url]);

  /** Dispatch incoming messages to the appropriate stores */
  const dispatch = useCallback((msg: RxMessage) => {
    const session = useSessionStore.getState();
    const chat = useChatStore.getState();

    switch (msg.type) {
      // ── Agent verbal output ──
      case "agent-text-chunk":
        chat.appendStreamingText(msg.text);
        break;

      case "agent-text-end":
        chat.commitStreamingText();
        break;

      // ── Silent UI state updates (from Agent tool-call side-effects) ──
      case "supervision-state-change":
        session.applyStateChange(msg.state, {
          duration: msg.duration,
          task: msg.task,
          pauseDuration: msg.pauseDuration,
          reason: msg.reason,
        });
        break;

      case "balance-update":
        session.applyBalanceUpdate(msg.balance, msg.change, msg.reason);
        break;

      case "plan-update":
        session.applyPlanUpdate(msg.plan);
        break;

      case "timer-sync":
        session.applyTimerSync(msg.remainingSeconds, msg.totalSeconds);
        break;

      case "supervision-alert":
        session.applyAlert(msg.message, msg.severity, msg.streakCount);
        break;

      case "tool-call-status":
        session.setActiveToolCall(
          msg.status === "calling" ? { tool: msg.tool, status: msg.status } : null,
        );
        break;

      // audio, model-info, control are handled by onMessage callback
      // (Live2D expression, lip-sync, etc.)
      default:
        break;
    }
  }, []);

  /** Send a message to backend */
  const send = useCallback((msg: TxMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn("[WS] Not connected, cannot send:", msg.type);
      return;
    }
    ws.send(JSON.stringify(msg));
  }, []);

  /** Close the connection */
  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current);
    reconnectCountRef.current = MAX_RECONNECT_ATTEMPTS; // prevent reconnect
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
  }, []);

  // Connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return { send, connect, disconnect };
}
