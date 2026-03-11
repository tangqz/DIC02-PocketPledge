/* ────────────────────────────────────────────────
 *  MessageBubble  –  Individual chat message
 * ──────────────────────────────────────────────── */
import { memo } from "react";
import type { ChatMessage } from "@/stores/chatStore";

interface Props {
  message: ChatMessage;
}

function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={`mb-3 flex ${isUser ? "justify-end" : "justify-start"} animate-slide-up`}
    >
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
          isUser
            ? "rounded-tr-sm bg-accent/20 text-white"
            : "rounded-tl-sm bg-surface-elevated text-white/90"
        }`}
      >
        <p className="text-sm leading-relaxed whitespace-pre-wrap">
          {message.text}
        </p>
        <time className="mt-1 block text-right text-[10px] text-white/30">
          {new Date(message.timestamp).toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </time>
      </div>
    </div>
  );
}

// ⚡ Bolt: memoize to prevent unnecessary re-renders when streamingText updates in parent ChatPanel
export default memo(MessageBubble);
