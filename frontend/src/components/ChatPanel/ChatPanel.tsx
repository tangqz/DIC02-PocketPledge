/* ────────────────────────────────────────────────
 *  ChatPanel  –  Subtitle area + streaming text + message history
 * ──────────────────────────────────────────────── */
import { useEffect, useRef } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import MessageBubble from "./MessageBubble";
import TextInput from "./TextInput";
import { useI18n } from "@/lib/i18n";

interface ChatPanelProps {
  /** When true, show full chat history; otherwise show only subtitle bar */
  expanded?: boolean;
  onSendText?: (text: string) => void;
}

export default function ChatPanel({
  expanded = false,
  onSendText,
}: ChatPanelProps) {
  const { messages, streamingText, isAgentSpeaking } = useChatStore();
  const activeToolCall = useSessionStore((s) => s.activeToolCall);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { t } = useI18n();

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  // ── Compact subtitle-only view (Focus mode) ──
  if (!expanded) {
    const latestText =
      streamingText ||
      (messages.length > 0 ? messages[messages.length - 1].text : "");

    return (
      <div className="pointer-events-none w-full px-6 pb-6">
        <div className="rounded-xl bg-surface-glass px-5 py-3 backdrop-blur-xl">
          {activeToolCall?.status === "calling" && (
            <div className="mb-2 flex items-center justify-center gap-2 text-xs font-medium text-accent">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
              系统正在处理您的请求
            </div>
          )}
          <p className="text-center text-sm leading-relaxed text-white/90">
            {latestText || (
              <span className="text-white/40">{t("focus.subtitle")}</span>
            )}
            {isAgentSpeaking && (
              <span className="ml-1 inline-block h-3 w-3 animate-breathing rounded-full bg-accent" />
            )}
          </p>
        </div>
      </div>
    );
  }

  // ── Expanded chat view ──
  return (
    <div className="flex h-full flex-col">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {activeToolCall?.status === "calling" && (
          <div className="mb-3 flex justify-center">
            <div className="rounded-2xl border border-accent/30 bg-accent/10 px-4 py-2 text-sm font-medium text-accent backdrop-blur-sm">
              系统正在处理您的请求
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Streaming text (agent typing) */}
        {streamingText && (
          <div className="mb-3 flex justify-start">
            <div className="max-w-[75%] rounded-2xl rounded-tl-sm bg-surface-elevated px-4 py-2.5">
              <p className="text-sm leading-relaxed text-white/90">
                {streamingText}
                <span className="ml-1 inline-block h-4 w-0.5 animate-pulse bg-accent" />
              </p>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Text input */}
      {onSendText && <TextInput onSend={onSendText} />}
    </div>
  );
}
