from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from app.business.crud import (
    list_assessment_results,
    list_meal_journal_entries,
    list_mood_entries,
)
from app.business.models import SessionLocal
from app.gateway.session import SessionState
from app.media_ai.client_factory import get_agent_client


logger = logging.getLogger(__name__)


@dataclass
class SystemDirective:
    action: Literal["none", "mood", "profile"] = "none"
    mood_data: dict | None = None
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
        client = get_agent_client()
        try:
            logger.info(
                "system agent request started, session_id=%s text=%s", session_id, text
            )

            try:
                user_id = int(session_id)
            except ValueError:
                user_id = None

            outputs = await client.run_system_agent(
                session_id=session_id,
                inputs=self._build_inputs(text, session, user_id),
            )
            logger.info(
                "system agent request succeeded, session_id=%s outputs=%s",
                session_id,
                outputs,
            )
        except Exception as exc:
            logger.exception("system agent workflow failed, session_id=%s", session_id)
            return SystemDirective(
                approved=False,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        return self._parse_outputs(outputs)

    def _build_inputs(
        self,
        text: str,
        session: SessionState,
        user_id: int | None,
    ) -> dict[str, Any]:
        inputs: dict[str, Any] = {
            "user_text": text,
            "chat_history": session.format_chat_history(),
            "language_mode": session.language_mode,
            "character_id": session.character_id,
        }
        if user_id is not None:
            inputs.update(self._load_behavior_context(user_id, session.language_mode))
        return inputs

    def _load_behavior_context(self, user_id: int, language_mode: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            mood_items = self._coerce_items(
                list_mood_entries(db=db, user_id=user_id, limit=12, days=14).get("items")
            )
            meal_items = self._coerce_items(
                list_meal_journal_entries(
                    db=db,
                    user_id=user_id,
                    limit=8,
                    days=14,
                ).get("items")
            )
            assessment_items = self._coerce_items(
                list_assessment_results(
                    db=db,
                    user_id=user_id,
                    limit=6,
                    days=30,
                ).get("items")
            )
        except Exception:
            logger.exception(
                "failed loading behavior context for system agent, user_id=%s", user_id
            )
            return {}
        finally:
            db.close()

        recent_moods = self._compact_moods(mood_items)
        recent_meals = self._compact_meals(meal_items)
        recent_assessments = self._compact_assessments(assessment_items)

        return {
            "recent_moods": recent_moods,
            "recent_meals": recent_meals,
            "recent_assessments": recent_assessments,
            "recent_mood_summary": self._build_mood_summary(recent_moods, language_mode),
            "recent_meal_summary": self._build_meal_summary(recent_meals, language_mode),
            "recent_assessment_summary": self._build_assessment_summary(
                recent_assessments,
                language_mode,
            ),
        }

    def _coerce_items(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _short_text(self, value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _compact_moods(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for item in items[:8]:
            compact.append(
                {
                    "emotion": str(item.get("emotion") or "neutral"),
                    "intensity": int(item.get("intensity") or 1),
                    "context": self._short_text(item.get("context"), 90),
                    "meal_info": self._short_text(item.get("meal_info"), 80),
                    "created_at": str(item.get("created_at") or ""),
                }
            )
        return compact

    def _compact_meals(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for item in items[:6]:
            compact.append(
                {
                    "meal_info": self._short_text(item.get("meal_info"), 90),
                    "meal_emotion": str(
                        item.get("meal_emotion") or item.get("emotion") or "neutral"
                    ),
                    "intensity": int(item.get("intensity") or 1),
                    "context": self._short_text(item.get("context"), 80),
                    "created_at": str(item.get("created_at") or ""),
                }
            )
        return compact

    def _compact_assessments(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for item in items[:6]:
            compact.append(
                {
                    "assessment_type": str(item.get("assessment_type") or ""),
                    "score": int(item.get("score") or 0),
                    "severity": str(item.get("severity") or "unknown"),
                    "positive_screen": bool(item.get("positive_screen") or False),
                    "created_at": str(item.get("created_at") or ""),
                }
            )
        return compact

    def _build_mood_summary(
        self,
        moods: list[dict[str, Any]],
        language_mode: str,
    ) -> str:
        is_en = str(language_mode).strip().lower() == "en"
        if not moods:
            return "No recent mood records." if is_en else "暂无近期情绪记录。"

        latest = moods[0]
        counter = Counter(str(item.get("emotion") or "neutral") for item in moods)
        top_parts = [f"{emo}:{cnt}" for emo, cnt in counter.most_common(3)]
        top_text = ", ".join(top_parts)

        if is_en:
            return (
                f"Latest mood {latest.get('emotion', 'neutral')} "
                f"({latest.get('intensity', 1)}/5); recent distribution {top_text}."
            )
        return (
            f"最近一次情绪：{latest.get('emotion', 'neutral')}"
            f"（{latest.get('intensity', 1)}/5）；近14天分布：{top_text}。"
        )

    def _build_meal_summary(
        self,
        meals: list[dict[str, Any]],
        language_mode: str,
    ) -> str:
        is_en = str(language_mode).strip().lower() == "en"
        if not meals:
            return (
                "No recent meal-mood records."
                if is_en
                else "暂无近期饮食与情绪记录。"
            )

        latest = meals[0]
        meal_text = self._short_text(latest.get("meal_info"), 40) or "n/a"
        latest_emotion = latest.get("meal_emotion", "neutral")
        latest_intensity = latest.get("intensity", 1)
        count = len(meals)

        if is_en:
            return (
                f"Recent meal logs: {count}; latest '{meal_text}', "
                f"emotion {latest_emotion} ({latest_intensity}/5)."
            )
        return (
            f"近期饮食记录 {count} 条；最新“{meal_text}”，"
            f"对应情绪 {latest_emotion}（{latest_intensity}/5）。"
        )

    def _build_assessment_summary(
        self,
        assessments: list[dict[str, Any]],
        language_mode: str,
    ) -> str:
        is_en = str(language_mode).strip().lower() == "en"
        if not assessments:
            return (
                "No recent self-assessment records."
                if is_en
                else "暂无近期心理自测记录。"
            )

        latest_by_type: dict[str, dict[str, Any]] = {}
        for item in assessments:
            key = str(item.get("assessment_type") or "").strip().lower()
            if not key or key in latest_by_type:
                continue
            latest_by_type[key] = item

        parts: list[str] = []
        for key in ("phq2", "gad2"):
            data = latest_by_type.get(key)
            if not data:
                continue
            parts.append(
                f"{key}={data.get('score', 0)}({data.get('severity', 'unknown')})"
            )

        if not parts:
            parts = [
                f"{item.get('assessment_type', 'assessment')}={item.get('score', 0)}"
                for item in assessments[:2]
            ]

        joined = ", ".join(parts)
        if is_en:
            return f"Recent screening summary: {joined}."
        return f"近期心理自测摘要：{joined}。"

    def _parse_outputs(self, outputs: dict[str, Any]) -> SystemDirective:
        return SystemDirective(
            action=self._coerce_action(outputs.get("action")),
            mood_data=self._coerce_mood_data(outputs.get("mood_data")),
            system_events=self._coerce_string_list(outputs.get("system_events")),
            approved=self._coerce_bool(outputs.get("approved"), default=True),
            requires_capture=self._coerce_bool(
                outputs.get("requires_capture"), default=False
            ),
            capture_sources=self._coerce_capture_sources(
                outputs.get("capture_sources")
            ),
        )

    async def extract_profile_memories(
        self,
        session_id: str,
        rotated_chat: str,
        existing_profile: str,
    ) -> list[str]:
        """Extract profile-worthy memory lines from rotated chat chunks."""
        client = get_agent_client()
        extract_method = getattr(client, "extract_profile_memories", None)
        if extract_method is None:
            return []

        try:
            outputs = await extract_method(
                session_id=session_id,
                inputs={
                    "rotated_chat": rotated_chat,
                    "existing_profile": existing_profile,
                },
            )
        except Exception:
            logger.exception(
                "profile memory extraction failed, session_id=%s", session_id
            )
            return []

        if not isinstance(outputs, dict):
            return []

        if not self._coerce_bool(outputs.get("should_update"), default=False):
            return []

        return self._coerce_profile_lines(outputs.get("memory_lines"))

    def _coerce_action(
        self, value: Any
    ) -> Literal["none", "mood", "profile"]:
        normalized = str(value or "none").strip().lower()
        if normalized in {"mood", "profile"}:
            return normalized  # type: ignore[return-value]
        return "none"

    def _coerce_mood_data(self, value: Any) -> dict | None:
        if value is None:
            return None
        if isinstance(value, dict) and value.get("emotion"):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict) and parsed.get("emotion"):
                    return parsed
            except json.JSONDecodeError:
                pass
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
        sources = [
            source
            for source in self._coerce_string_list(value)
            if source in {"camera", "screen"}
        ]
        return sources

    def _coerce_profile_lines(self, value: Any) -> list[str]:
        lines = self._coerce_string_list(value)
        normalized: list[str] = []
        seen: set[str] = set()
        for line in lines:
            text = line.strip()
            if not text:
                continue
            if not text.startswith("-"):
                text = f"- {text}"
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
            if len(normalized) >= 3:
                break
        return normalized
