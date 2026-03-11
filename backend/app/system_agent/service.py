from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from app.gateway.session import SessionState
from app.media_ai.dify_proxy import get_dify_client


logger = logging.getLogger(__name__)


@dataclass
class SystemDirective:
    action: Literal["none", "plan", "start", "pause", "resume", "complete"] = "none"
    duration_seconds: int | None = None
    pause_seconds: int | None = None
    plan: dict | None = None
    system_events: list[str] = field(default_factory=list)
    approved: bool = True
    requires_capture: bool = False
    capture_sources: list[str] = field(default_factory=list)
    error_message: str | None = None


class SystemAgentService:
    async def build_directive(
        self,
        session_id: str,
        text: str,
        session: SessionState,
    ) -> SystemDirective:
        client = get_dify_client()
        try:
            logger.info("system agent request started, session_id=%s text=%s", session_id, text)
            outputs = await client.run_system_agent(
                session_id=session_id,
                inputs=self._build_inputs(text, session),
            )
            logger.info("system agent request succeeded, session_id=%s outputs=%s", session_id, outputs)
        except Exception as exc:
            logger.exception("system agent workflow failed, session_id=%s", session_id)
            return SystemDirective(
                approved=False,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        return self._parse_outputs(outputs)

    def _build_inputs(self, text: str, session: SessionState) -> dict[str, Any]:
        return {
            "user_text": text,
            "chat_history": session.format_chat_history(),
            "language_mode": session.language_mode,
            "character_id": session.character_id,
            "supervision_state": session.supervision_state,
            "current_task": session.current_plan or "",
            "total_focus_seconds": session.total_focus_seconds or 0,
            "focus_time_remaining": session.focus_time_remaining or 0,
            "suggested_focus_seconds": session.suggested_focus_seconds or 0,
            "pause_remaining_seconds": session.pause_remaining_seconds or 0,
            "pause_requests_count": session.pause_requests_count,
            "is_bankrupt": str(session.is_bankrupt).lower(),
        }

    def _parse_outputs(self, outputs: dict[str, Any]) -> SystemDirective:
        return SystemDirective(
            action=self._coerce_action(outputs.get("action")),
            duration_seconds=self._coerce_optional_int(outputs.get("duration_seconds")),
            pause_seconds=self._coerce_optional_int(outputs.get("pause_seconds")),
            plan=self._coerce_plan(outputs.get("plan")),
            system_events=self._coerce_string_list(outputs.get("system_events")),
            approved=self._coerce_bool(outputs.get("approved"), default=True),
            requires_capture=self._coerce_bool(outputs.get("requires_capture"), default=False),
            capture_sources=self._coerce_capture_sources(outputs.get("capture_sources")),
        )

    def _coerce_action(self, value: Any) -> Literal["none", "plan", "start", "pause", "resume", "complete"]:
        normalized = str(value or "none").strip().lower()
        if normalized in {"plan", "start", "pause", "resume", "complete"}:
            return normalized  # type: ignore[return-value]
        return "none"

    def _coerce_optional_int(self, value: Any) -> int | None:
        if value in (None, "", 0, "0"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _coerce_bool(self, value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
        return default

    def _coerce_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [line.strip() for line in stripped.splitlines() if line.strip()]
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        return []

    def _coerce_capture_sources(self, value: Any) -> list[str]:
        sources = [source for source in self._coerce_string_list(value) if source in {"camera", "screen"}]
        return sources

    def _coerce_plan(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                return parsed
        return None
