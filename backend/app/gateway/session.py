from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    """Per-WebSocket in-memory state for companion session.

    No supervision state machine — the companion is always active
    as long as the WebSocket connection is open.
    """

    session_ref: str | None = None
    # ── Emotion tracking ──
    current_emotion: dict[str, Any] | None = None
    emotion_history: list[dict[str, Any]] = field(default_factory=list)
    # ── Chat ring buffer ──
    chat_history: list[dict[str, str]] = field(default_factory=list)
    profile_rollover_buffer: list[dict[str, str]] = field(default_factory=list)
    # ── Capture (for <<CAPTURE>> mechanism) ──
    pending_capture_request_id: str | None = None
    pending_capture_prompt: str | None = None
    pending_capture_sources: list[str] = field(default_factory=list)
    pending_capture_mode: str = "system-agent"
    # ── Vision timeline (for temporal stitching) ──
    image_timeline: list[tuple[float, list[dict[str, Any]]]] = field(
        default_factory=list
    )
    # ── Locale / character ──
    language_mode: str = "zh"
    character_id: str = "milly"

    MAX_HISTORY_TURNS: int = 50
    PROFILE_ROLLOVER_BATCH: int = 25

    def append_chat(self, role: str, content: str) -> None:
        """Append a message to the chat history ring buffer."""
        self.chat_history.append({"role": role, "content": content})
        if len(self.chat_history) > self.MAX_HISTORY_TURNS:
            overflow_count = len(self.chat_history) - self.MAX_HISTORY_TURNS
            overflow_items = self.chat_history[:overflow_count]
            self.chat_history = self.chat_history[overflow_count:]
            self.profile_rollover_buffer.extend(overflow_items)

    def pop_profile_rollover_batch(self) -> list[dict[str, str]]:
        """Return one full rollover batch once 25 old messages have rotated out."""
        if len(self.profile_rollover_buffer) < self.PROFILE_ROLLOVER_BATCH:
            return []
        batch = self.profile_rollover_buffer[: self.PROFILE_ROLLOVER_BATCH]
        self.profile_rollover_buffer = self.profile_rollover_buffer[
            self.PROFILE_ROLLOVER_BATCH :
        ]
        return batch

    def clear_chat_context(self) -> None:
        """Clear chat history and rollover buffers."""
        self.chat_history = []
        self.profile_rollover_buffer = []

    def format_chat_history(self) -> str:
        """Format recent chat history as a readable string for the system agent."""
        lines = []
        for msg in self.chat_history:
            prefix = "用户" if msg["role"] == "user" else "暖伴"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    def record_emotion(self, emotion_data: dict[str, Any]) -> None:
        """Record an emotion detection result."""
        self.current_emotion = emotion_data
        self.emotion_history.append(emotion_data)
        if len(self.emotion_history) > 200:
            self.emotion_history = self.emotion_history[-200:]

    def set_pending_capture(
        self,
        request_id: str,
        prompt: str,
        sources: list[str],
        mode: str = "system-agent",
    ) -> None:
        self.pending_capture_request_id = request_id
        self.pending_capture_prompt = prompt
        self.pending_capture_sources = list(sources)
        self.pending_capture_mode = mode

    def clear_pending_capture(self) -> None:
        self.pending_capture_request_id = None
        self.pending_capture_prompt = None
        self.pending_capture_sources = []
        self.pending_capture_mode = "system-agent"
