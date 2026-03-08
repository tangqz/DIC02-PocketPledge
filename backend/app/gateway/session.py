from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


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
    pause_remaining_seconds: int | None = None

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
        self.total_focus_seconds = duration_seconds
        self.focus_time_remaining = duration_seconds
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
