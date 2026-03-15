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
import { useAuthStore } from "@/stores/authStore";
import { useCharacterStore } from "@/stores/characterStore";
import type { TxMessage, RxMessage } from "@/lib/protocol";

export interface UseWebSocketOptions {
  /** WebSocket URL (default: ws://localhost:12393/ws) */
  url?: string;
  /** Called when an RxMessage is received (for audio/model-info/control) */
  onMessage?: (msg: RxMessage) => void;
  /** Auto-connect on mount? */
  autoConnect?: boolean;
}

const resolveDefaultWsUrl = (): string => {
  const envUrl = import.meta.env.VITE_WS_URL as string | undefined;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.trim();
  }

  // In dev mode (Vite dev server) connect directly to the backend port.
  // In production builds (Docker + nginx) follow the current host so the
  // nginx reverse proxy can handle the /ws path.
  if (import.meta.env.DEV) {
    return "ws://localhost:12393/ws";
  }

  if (typeof window !== "undefined") {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProtocol}//${window.location.host}/ws`;
  }

  return "ws://localhost:12393/ws";
};

const DEFAULT_URL = resolveDefaultWsUrl();
const RECONNECT_DELAY = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

export function useWebSocket({
  url = DEFAULT_URL,
  onMessage,
  autoConnect = true,
}: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const pendingMessagesRef = useRef<TxMessage[]>([]);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const manualCloseRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const { setIsConnected } = useSessionStore.getState();

  const flushPendingMessages = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || pendingMessagesRef.current.length === 0) {
      return;
    }

    const queued = pendingMessagesRef.current.splice(0, pendingMessagesRef.current.length);
    for (const msg of queued) {
      ws.send(JSON.stringify(msg));
    }
    console.log("[WS] Flushed queued messages:", queued.map((msg) => msg.type));
  }, []);

  const connect = useCallback(() => {
    // Don't double-connect
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    // Attach JWT token as query param for WS authentication
    const token = useAuthStore.getState().token;
    const selectedCharacterId = useCharacterStore.getState().selectedCharacterId;
    if (!token) {
      console.warn("[WS] No auth token, cannot connect");
      return;
    }
    const wsUrl = `${url}?token=${encodeURIComponent(token)}&characterId=${encodeURIComponent(selectedCharacterId || "")}`;
    manualCloseRef.current = false;
    clearTimeout(reconnectTimerRef.current);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    console.log("[WS] Connecting to", wsUrl);

    ws.onopen = () => {
      if (wsRef.current !== ws) {
        return;
      }
      console.log("[WS] Connected to", url);
      setIsConnected(true);
      reconnectCountRef.current = 0;
      flushPendingMessages();
    };

    ws.onclose = (event) => {
      if (wsRef.current !== ws) {
        return;
      }
      console.log("[WS] Disconnected", { code: event.code, reason: event.reason });
      setIsConnected(false);
      wsRef.current = null;

      // Auto-reconnect
      if (!manualCloseRef.current && reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectCountRef.current++;
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY);
      }
    };

    ws.onerror = (err) => {
      if (wsRef.current !== ws) {
        return;
      }
      console.error("[WS] Error:", err);
      ws.close();
    };

    ws.onmessage = (event) => {
      if (wsRef.current !== ws) {
        return;
      }
      try {
        const msg = JSON.parse(event.data) as RxMessage;
        dispatch(msg);
        onMessageRef.current?.(msg);
      } catch (err) {
        console.warn("[WS] Invalid message:", err);
      }
    };
  }, [flushPendingMessages, url]);

  /** Dispatch incoming messages to the appropriate stores */
  const dispatch = useCallback((msg: RxMessage) => {
    const session = useSessionStore.getState();
    const chat = useChatStore.getState();

    switch (msg.type) {
      // ── Agent verbal output ──
      case "agent-text-chunk":
        chat.appendStreamingText(msg.text);
        break;

      case "user-transcript":
        console.log("[WS] Received user transcript:", msg.text);
        chat.addMessage("user", msg.text);
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
      pendingMessagesRef.current.push(msg);
      console.warn("[WS] Not connected, queueing:", msg.type, "queueSize=", pendingMessagesRef.current.length);
      if (!ws || ws.readyState === WebSocket.CLOSED) {
        connect();
      }
      return;
    }
    ws.send(JSON.stringify(msg));
  }, [connect]);

  /** Close the connection */
  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current);
    manualCloseRef.current = true;
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
