from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


ALLOWED_TRANSITIONS = {
    "setup": {"active"},
    "active": {"paused", "completed"},
    "paused": {"active", "completed"},
    "completed": set(),
}


@dataclass
class SessionState:
    """Per-WebSocket in-memory state for supervision and timer management."""

    supervision_state: str = "setup"
    start_time: datetime | None = None
    focus_time_remaining: int | None = None
    total_focus_seconds: int | None = None
    distraction_streak: int = 0
    is_bankrupt: bool = False
    current_plan: str | None = None
    current_plan_data: dict[str, Any] | None = None
    session_ref: str | None = None
    pause_remaining_seconds: int | None = None
    suggested_focus_seconds: int | None = None
    pause_requests_count: int = 0
    pending_capture_request_id: str | None = None
    pending_capture_prompt: str | None = None
    pending_capture_sources: list[str] = field(default_factory=list)
    pending_capture_mode: str = "system-agent"
    chat_history: list[dict[str, str]] = field(default_factory=list)
    image_timeline: list[tuple[float, list[dict[str, Any]]]] = field(
        default_factory=list
    )
    language_mode: str = "zh"
    character_id: str = "milly"

    MAX_HISTORY_TURNS: int = 30

    def append_chat(self, role: str, content: str) -> None:
        """Append a message to the chat history ring buffer."""
        self.chat_history.append({"role": role, "content": content})
        if len(self.chat_history) > self.MAX_HISTORY_TURNS:
            self.chat_history = self.chat_history[-self.MAX_HISTORY_TURNS :]

    def format_chat_history(self) -> str:
        """Format recent chat history as a readable string for the system agent."""
        lines = []
        for msg in self.chat_history:
            prefix = "用户" if msg["role"] == "user" else "米莉"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    @property
    def remaining_seconds(self) -> int | None:
        """Backward-compatible alias for focus_time_remaining."""
        return self.focus_time_remaining

    @remaining_seconds.setter
    def remaining_seconds(self, value: int | None) -> None:
        self.focus_time_remaining = value

    @property
    def total_seconds(self) -> int | None:
        """Backward-compatible alias for total_focus_seconds."""
        return self.total_focus_seconds

    @total_seconds.setter
    def total_seconds(self, value: int | None) -> None:
        self.total_focus_seconds = value

    def transition(self, new_state: str) -> None:
        """Apply a supervision state transition with strict validation."""
        if new_state == self.supervision_state:
            return

        allowed_targets = ALLOWED_TRANSITIONS.get(self.supervision_state, set())
        if new_state not in allowed_targets:
            raise ValueError(
                f"Invalid transition: {self.supervision_state} -> {new_state}"
            )

        if new_state == "active" and self.start_time is None:
            self.start_time = datetime.now(UTC)

        self.supervision_state = new_state

    def start(self, duration_seconds: int) -> None:
        """Start supervision from setup and initialize timer."""
        if self.supervision_state == "completed":
            # Allow starting a new focus session after completion without forcing reconnect.
            self.supervision_state = "setup"
            self.start_time = None
            self.pause_remaining_seconds = None
        self.total_focus_seconds = duration_seconds
        self.focus_time_remaining = duration_seconds
        self.pause_requests_count = 0
        self.transition("active")

    def pause(self, duration_seconds: int | None = None) -> None:
        """Pause supervision and optionally set a pause timeout."""
        self.transition("paused")
        self.pause_remaining_seconds = duration_seconds

    def resume(self) -> None:
        """Resume supervision from paused state."""
        self.transition("active")
        self.pause_remaining_seconds = None

    def complete(self) -> None:
        """Mark supervision as completed."""
        self.transition("completed")
        self.pause_remaining_seconds = None
        self.pause_requests_count = 0

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

    def tick(self) -> bool:
        """Advance one timer tick and return True when countdown reaches zero."""
        if self.supervision_state != "active":
            return False

        if self.focus_time_remaining is None:
            return False

        if self.focus_time_remaining > 0:
            self.focus_time_remaining -= 1

        return self.focus_time_remaining == 0

    def tick_pause(self) -> bool:
        """Advance paused countdown and return True when pause timeout expires."""
        if self.supervision_state != "paused":
            return False

        if self.pause_remaining_seconds is None:
            return False

        if self.pause_remaining_seconds > 0:
            self.pause_remaining_seconds -= 1

        return self.pause_remaining_seconds == 0
