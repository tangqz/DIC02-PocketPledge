from __future__ import annotations

import asyncio
import json
import uuid
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Coroutine

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth.security import decode_access_token
from app.business.models import SessionLocal
from app.business.crud import (
    PENALTY_PER_DISTRACTION,
    append_user_profile_memory as db_append_user_profile_memory,
    create_chat_message as db_create_chat_message,
    create_session_summary as db_create_session_summary,
    execute_penalty as db_execute_penalty,
    get_active_plan as db_get_active_plan,
    get_user_profile_document as db_get_user_profile_document,
    get_user_status as db_get_user_status,
    list_recent_chat_messages as db_list_recent_chat_messages,
    record_pause_request as db_record_pause_request,
    start_focus_session as db_start_focus_session,
    upsert_study_plan as db_upsert_study_plan,
)
from app.gateway.session import SessionState
from app.media_ai import (
    evaluate_start_readiness,
    evaluate_vision,
    process_text_chat,
    transcribe_audio,
)
from app.system_agent import SystemAgentService

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manage active websocket connections and in-memory session states."""

    def __init__(self, reconnect_ttl_seconds: int = 300) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.user_states: dict[str, SessionState] = {}
        self.disconnected_at: dict[str, datetime] = {}
        self.pending_messages: dict[str, list[dict[str, Any]]] = {}
        self.reconnect_ttl = timedelta(seconds=reconnect_ttl_seconds)

    async def connect(self, user_id: str, websocket: WebSocket) -> SessionState:
        """Accept websocket and return existing or new session state."""
        await websocket.accept()
        previous = self.active_connections.get(user_id)
        if previous is not None and previous is not websocket:
            await previous.close(code=1000, reason="replaced by new connection")

        self.active_connections[user_id] = websocket
        self.cleanup_expired_states()
        self.disconnected_at.pop(user_id, None)

        session = self.user_states.get(user_id)
        if session is None:
            session = SessionState()
            self.user_states[user_id] = session

        queued_messages = self.pending_messages.pop(user_id, [])
        if queued_messages:
            logger.info(
                "flushing queued ws messages user_id=%s count=%s",
                user_id,
                len(queued_messages),
            )
            for payload in queued_messages:
                await self.send_personal_message(user_id, payload)
        return session

    def disconnect(self, user_id: str, websocket: WebSocket | None = None) -> bool:
        """Mark one user as disconnected while preserving session for TTL.

        Returns True only when the disconnect applies to the currently active
        websocket. Stale websocket handlers must not clear a newer connection.
        """
        current = self.active_connections.get(user_id)
        if websocket is not None and current is not None and current is not websocket:
            logger.info("ignoring stale ws disconnect user_id=%s", user_id)
            return False

        if current is None and websocket is not None:
            return False

        self.active_connections.pop(user_id, None)
        self.disconnected_at[user_id] = datetime.now(UTC)
        self.cleanup_expired_states()
        return True

    async def send_personal_message(self, user_id: str, payload: dict) -> None:
        """Send one message to a specific active user."""
        websocket = self.active_connections.get(user_id)
        if websocket is None:
            logger.warning(
                "ws tx queued user_id=%s reason=no-active-connection payload=%s",
                user_id,
                _summarize_payload(payload),
            )
            self.pending_messages.setdefault(user_id, []).append(payload)
            return
        logger.info("ws tx user_id=%s payload=%s", user_id, _summarize_payload(payload))
        try:
            await websocket.send_json(payload)
        except Exception:
            logger.exception("ws tx failed, queueing for retry user_id=%s", user_id)
            if self.active_connections.get(user_id) is websocket:
                self.active_connections.pop(user_id, None)
            self.pending_messages.setdefault(user_id, []).append(payload)

    async def broadcast(self, payload: dict) -> None:
        """Broadcast one message to all active users."""
        for websocket in list(self.active_connections.values()):
            await websocket.send_json(payload)

    def cleanup_expired_states(self) -> None:
        """Delete disconnected user states that exceeded reconnect TTL."""
        now = datetime.now(UTC)
        expired_users = [
            user_id
            for user_id, disconnected_time in self.disconnected_at.items()
            if now - disconnected_time > self.reconnect_ttl
        ]
        for user_id in expired_users:
            self.disconnected_at.pop(user_id, None)
            self.user_states.pop(user_id, None)


manager = ConnectionManager(reconnect_ttl_seconds=300)

CHARACTER_CATALOG: dict[str, dict[str, Any]] = {
    "milly": {
        "name": "milly",
        "displayName": "Milly",
        "description": "Warm but strict study partner. Keeps pressure when needed.",
        "languageHints": ["zh", "en"],
        "personaStyle": "supportive-strict",
        "modelInfo": {
            "name": "mao_pro",
            "url": "/live2d-models/mao_pro/mao_pro.model3.json",
            "kScale": 0.5,
            "emotionMap": {
                "neutral": 0,
                "happy": 3,
                "encouraging": 4,
                "angry": 2,
                "proud": 7,
            },
            "idleMotionGroup": "Idle",
            "talkMotionGroup": "",
        },
    },
    "ren": {
        "name": "natori",
        "displayName": "Natori",
        "description": "Calm mentor companion. Rational, concise and disciplined.",
        "languageHints": ["zh", "en"],
        "personaStyle": "calm-mentor",
        "modelInfo": {
            "name": "natori_pro_zh",
            "url": "/live2d-models/natori_pro_zh/runtime/natori_pro_t06.model3.json",
            "kScale": 0.52,
            "emotionMap": {
                "neutral": 2,
                "happy": 4,
                "encouraging": 4,
                "angry": 0,
                "proud": 4,
            },
            "idleMotionGroup": "Idle",
            "talkMotionGroup": "Tap",
        },
    },
}
DEFAULT_CHARACTER_ID = "milly"

DEFAULT_TOTAL_SECONDS = 1500
DISTRACTION_THRESHOLD = 3
PENALTY_AMOUNT = PENALTY_PER_DISTRACTION
BOT_NAME = "Study Buddy"
DEFAULT_BALANCE = 100
SYS_MARKER = "<<SYS>>"
LOG_PREVIEW_LIMIT = 240
START_CAPTURE_SOURCES = ["camera", "screen"]
MAX_AGENT_STAGES = 6

watchdog_tasks: dict[str, asyncio.Task] = {}
audio_buffers: dict[str, list[float]] = {}
system_agent = SystemAgentService()


def _duration_to_minutes(duration_seconds: int | None) -> int | None:
    if duration_seconds is None:
        return None
    return max(1, duration_seconds // 60)


def _format_rmb_from_cents(cents: int) -> str:
    return f"{(int(cents) / 100):.2f}"


def _build_start_error_system_event(error_message: str | None) -> str:
    cleaned = str(error_message or "").strip()
    match = re.search(
        r"insufficient balance: need\s+(\d+),\s+have\s+(\d+)", cleaned, re.IGNORECASE
    )
    if match:
        need = int(match.group(1))
        have = int(match.group(2))
        return (
            "[SYSTEM_RESULT: START_REJECTED, CODE: insufficient_balance, "
            f"NEED_RMB: {_format_rmb_from_cents(need)}, HAVE_RMB: {_format_rmb_from_cents(have)}]"
        )
    if cleaned:
        detail = cleaned.replace("]", " ").replace("\n", " ").strip()
        return f"[SYSTEM_RESULT: START_REJECTED, CODE: generic_error, DETAIL: {detail}]"
    return "[SYSTEM_RESULT: START_REJECTED, CODE: generic_error]"


def _build_start_outcome_system_events(
    start_result: dict[str, Any] | None, duration_seconds: int
) -> list[str]:
    if start_result and start_result.get("ok"):
        upfront_cost_cents = int(start_result.get("upfront_cost", 0))
        return [
            f"[SYSTEM_RESULT: SESSION_STARTED, MINUTES: {max(duration_seconds // 60, 1)}, COST_RMB: {_format_rmb_from_cents(upfront_cost_cents)}]"
        ]

    return [_build_start_error_system_event((start_result or {}).get("error"))]


def _build_fallback_system_events(
    directive: Any,
    session: SessionState,
    extra: dict[str, Any] | None = None,
) -> list[str]:
    if directive.system_events:
        return [str(event) for event in directive.system_events if str(event).strip()]

    details = extra or {}
    if directive.action == "start":
        minutes = details.get("minutes") or _duration_to_minutes(
            directive.duration_seconds
        )
        cost = details.get("cost")
        if cost is not None:
            return [
                f"[SYSTEM_RESULT: SESSION_STARTED, MINUTES: {minutes}, COST_RMB: {_format_rmb_from_cents(int(cost))}]"
            ]
        return [f"[SYSTEM_RESULT: SESSION_STARTED, MINUTES: {minutes}]"]
    if directive.action == "pause":
        if directive.approved:
            minutes = details.get("minutes") or _duration_to_minutes(
                directive.pause_seconds
            )
            return [f"[SYSTEM_RESULT: PAUSE_APPROVED, MINUTES: {minutes}]"]
        reason = details.get("reason") or "此次暂停审核未通过"
        return [f"[SYSTEM_RESULT: PAUSE_REJECTED, REASON: {reason}]"]
    if directive.action == "resume":
        return ["[SYSTEM_RESULT: RESUME_APPROVED]"]
    if directive.action == "complete":
        return ["[SYSTEM_RESULT: SESSION_COMPLETED]"]
    if directive.action == "plan" and session.current_plan_data:
        total_minutes = session.current_plan_data.get("totalMinutes")
        title = session.current_plan or "学习计划"
        return [
            f"[SYSTEM_RESULT: PLAN_UPDATED, TITLE: {title}, TOTAL_MINUTES: {total_minutes}]"
        ]
    return []


def _first_task_title(plan: dict[str, Any] | None) -> str | None:
    if not plan:
        return None
    tasks = plan.get("tasks") or []
    if not tasks:
        return None
    return str(tasks[0].get("title") or "").strip() or None


def _has_system_result(system_events: list[str], keyword: str) -> bool:
    return any(keyword in str(event) for event in system_events)


def _plan_focus_seconds(plan: dict[str, Any] | None) -> int | None:
    if not plan:
        return None

    suggested_duration = plan.get("suggestedDuration")
    try:
        normalized_suggested = int(str(suggested_duration).strip())
    except (TypeError, ValueError):
        normalized_suggested = 0

    tasks = plan.get("tasks") or []
    first_task = tasks[0] if tasks else None
    first_task_minutes = (
        first_task.get("estimatedMinutes") if isinstance(first_task, dict) else None
    )
    try:
        normalized_first_minutes = int(str(first_task_minutes).strip())
    except (TypeError, ValueError):
        normalized_first_minutes = 0

    if normalized_first_minutes > 0:
        first_task_seconds = normalized_first_minutes * 60
        if (
            normalized_suggested <= 0
            or abs(normalized_suggested - first_task_seconds) >= 60
        ):
            return first_task_seconds

    if normalized_suggested > 0:
        return normalized_suggested

    total_minutes = plan.get("totalMinutes")
    try:
        normalized_total_minutes = int(str(total_minutes).strip())
    except (TypeError, ValueError):
        normalized_total_minutes = 0

    if normalized_total_minutes > 0 and len(tasks) <= 1:
        return normalized_total_minutes * 60

    return None


def _build_completion_summary(session: SessionState) -> tuple[str, dict[str, Any]]:
    total_seconds = session.total_focus_seconds or 0
    remaining_seconds = session.focus_time_remaining or 0
    focused_seconds = max(total_seconds - remaining_seconds, 0)
    focused_minutes = focused_seconds // 60
    summary_text = (
        f"任务：{session.current_plan or '未命名任务'}；"
        f"本次已专注约 {focused_minutes} 分钟；"
        f"暂停申请 {session.pause_requests_count} 次；"
        f"当前余额状态：{'已触发降级' if session.is_bankrupt else '正常'}。"
    )
    meta = {
        "current_task": session.current_plan,
        "focused_seconds": focused_seconds,
        "total_focus_seconds": total_seconds,
        "pause_requests_count": session.pause_requests_count,
        "is_bankrupt": session.is_bankrupt,
    }
    return summary_text, meta


async def _persist_active_plan(
    user_id: str, plan: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        uid = int(user_id)
    except ValueError:
        return None
    db = SessionLocal()
    try:
        return db_upsert_study_plan(db=db, user_id=uid, plan=plan)
    except Exception:
        logger.exception("failed to persist study plan, user_id=%s", user_id)
        return None
    finally:
        db.close()


async def _hydrate_session_plan(user_id: str, session: SessionState) -> None:
    if session.current_plan_data is not None:
        return
    try:
        uid = int(user_id)
    except ValueError:
        return
    db = SessionLocal()
    try:
        stored_plan = db_get_active_plan(db=db, user_id=uid)
    except Exception:
        logger.exception("failed to load active plan, user_id=%s", user_id)
        return
    finally:
        db.close()

    if stored_plan and stored_plan.get("plan"):
        session.current_plan_data = stored_plan["plan"]
        session.current_plan = _first_task_title(session.current_plan_data)
        resolved_focus_seconds = _plan_focus_seconds(session.current_plan_data)
        if resolved_focus_seconds is not None:
            session.suggested_focus_seconds = resolved_focus_seconds


async def _record_pause_request(
    user_id: str,
    session: SessionState,
    requested_text: str,
    approved: bool,
    pause_seconds: int | None,
    decision_reason: str,
) -> None:
    try:
        uid = int(user_id)
    except ValueError:
        return
    db = SessionLocal()
    try:
        db_record_pause_request(
            db=db,
            user_id=uid,
            requested_text=requested_text,
            approved=approved,
            pause_seconds=pause_seconds,
            decision_reason=decision_reason,
            session_ref=session.session_ref,
            meta={
                "supervision_state": session.supervision_state,
                "pause_requests_count": session.pause_requests_count,
            },
        )
    except Exception:
        logger.exception("failed to record pause request, user_id=%s", user_id)
    finally:
        db.close()


async def _persist_session_summary(user_id: str, session: SessionState) -> None:
    try:
        uid = int(user_id)
    except ValueError:
        return
    summary_text, meta = _build_completion_summary(session)
    db = SessionLocal()
    try:
        db_create_session_summary(
            db=db,
            user_id=uid,
            summary_text=summary_text,
            session_ref=session.session_ref,
            meta=meta,
        )
        profile_line = (
            f"- session_ref={session.session_ref or 'n/a'}; task={session.current_plan or 'untitled'}; "
            f"focused_minutes={meta.get('focused_seconds', 0) // 60}; "
            f"pause_requests={meta.get('pause_requests_count', 0)}; "
            f"bankrupt={meta.get('is_bankrupt', False)}"
        )
        db_append_user_profile_memory(db=db, user_id=uid, memory_line=profile_line)
    except Exception:
        logger.exception("failed to persist session summary, user_id=%s", user_id)
    finally:
        db.close()


async def _persist_chat_message(
    user_id: str, role: str, content: str, session_ref: str | None
) -> None:
    try:
        uid = int(user_id)
    except ValueError:
        return

    db = SessionLocal()
    try:
        db_create_chat_message(
            db=db,
            user_id=uid,
            role=role,
            content=content,
            session_ref=session_ref,
        )
    except Exception:
        logger.exception(
            "failed to persist chat message, user_id=%s role=%s", user_id, role
        )
    finally:
        db.close()


async def _append_chat(
    session: SessionState, user_id: str, role: str, content: str
) -> None:
    session.append_chat(role, content)
    await _persist_chat_message(
        user_id=user_id, role=role, content=content, session_ref=session.session_ref
    )


async def _hydrate_chat_history(user_id: str, session: SessionState) -> None:
    if session.chat_history:
        return
    try:
        uid = int(user_id)
    except ValueError:
        return

    db = SessionLocal()
    try:
        result = db_list_recent_chat_messages(
            db=db, user_id=uid, limit=session.MAX_HISTORY_TURNS
        )
    except Exception:
        logger.exception("failed to load chat history, user_id=%s", user_id)
        return
    finally:
        db.close()

    for item in result.get("items", []):
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant", "system"}:
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        session.chat_history.append({"role": role, "content": content})


def _split_sys_marker_buffer(buffer: str) -> tuple[str, str, bool]:
    """Split streamed text into emit/pending parts while guarding the SYS marker.

    Returns (emit_text, pending_text, sys_detected). The pending suffix is retained
    when it could still become the beginning of a future <<SYS>> marker.
    """
    if not buffer:
        return "", "", False

    marker_index = buffer.find(SYS_MARKER)
    if marker_index >= 0:
        return buffer[:marker_index], "", True

    max_prefix = min(len(buffer), len(SYS_MARKER) - 1)
    for prefix_len in range(max_prefix, 0, -1):
        if buffer.endswith(SYS_MARKER[:prefix_len]):
            return buffer[:-prefix_len], buffer[-prefix_len:], False

    return buffer, "", False


def _sanitize_agent_text(text: str) -> str:
    """Remove internal trigger markers from any user-visible agent text."""
    return text.replace(SYS_MARKER, "").replace("<<CAPTURE>>", "").strip()


def _can_start_session(session: SessionState) -> bool:
    return bool((session.current_plan or "").strip())


def _profile_has_minimum_basics(profile_content: str) -> bool:
    normalized = (profile_content or "").strip().lower()
    if not normalized:
        return False

    has_calling_hint = bool(
        re.search(
            r"(称呼|叫我|你可以叫我|nickname|call me|preferred name|name[:：])",
            normalized,
        )
    )
    has_education_hint = bool(
        re.search(
            r"(教育|学历|学校|年级|专业|本科|研究生|高中|初中|大学|education|school|major|grade|background)",
            normalized,
        )
    )
    return has_calling_hint and has_education_hint


async def _is_profile_ready_for_start(user_id: str) -> bool:
    try:
        uid = int(user_id)
    except ValueError:
        return False

    db = SessionLocal()
    try:
        profile_doc = db_get_user_profile_document(db=db, user_id=uid)
    except Exception:
        logger.exception(
            "failed to load user profile for start check, user_id=%s", user_id
        )
        return False
    finally:
        db.close()

    return _profile_has_minimum_basics(str(profile_doc.get("content", "")))


def _truncate_log_text(value: Any, limit: int = LOG_PREVIEW_LIMIT) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _summarize_payload(payload: dict[str, Any]) -> str:
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "audio" and isinstance(value, list):
            summary[key] = f"<{len(value)} samples>"
            continue
        if key == "audio" and isinstance(value, str):
            summary[key] = f"<{len(value)} base64 chars>"
            continue
        if key == "images" and isinstance(value, list):
            summary[key] = [
                {
                    "source": item.get("source"),
                    "mime_type": item.get("mime_type"),
                    "data": f"<{len(str(item.get('data', '')))} base64 chars>",
                }
                for item in value[:4]
                if isinstance(item, dict)
            ]
            if len(value) > 4:
                summary[key].append({"remaining": len(value) - 4})
            continue
        if isinstance(value, str):
            summary[key] = _truncate_log_text(value)
            continue
        if isinstance(value, dict):
            summary[key] = {
                nested_key: _truncate_log_text(nested_value)
                for nested_key, nested_value in value.items()
            }
            continue
        if isinstance(value, list):
            summary[key] = f"<list len={len(value)}>"
            continue
        summary[key] = value
    return json.dumps(summary, ensure_ascii=False)


def _normalize_system_events(events: list[str]) -> list[str]:
    normalized: list[str] = []
    for event in events:
        text = str(event).strip()
        if not text:
            continue
        if text.startswith("[SYSTEM_EVENT:"):
            text = text.replace("[SYSTEM_EVENT:", "[SYSTEM_RESULT:", 1)
        normalized.append(text)
    return normalized


async def get_user_balance(user_id: str) -> dict[str, int | bool]:
    """Query real balance from the database via business CRUD."""
    try:
        uid = int(user_id)
    except ValueError:
        return {"balance": 0, "is_bankrupt": True}
    db = SessionLocal()
    try:
        result = db_get_user_status(db, uid)
        return {"balance": result["balance"], "is_bankrupt": result["is_bankrupt"]}
    except Exception:
        return {"balance": 0, "is_bankrupt": True}
    finally:
        db.close()


async def deduct_penalty(user_id: str, amount: int) -> dict[str, int | bool]:
    """Execute penalty via real database transaction."""
    try:
        uid = int(user_id)
    except ValueError:
        return {"balance": 0, "is_bankrupt": True}
    db = SessionLocal()
    try:
        result = db_execute_penalty(
            db,
            uid,
            reason="检测到连续走神",
            distraction_count=1,
            penalty_amount=amount,
        )
        return {
            "balance": result["balance_after"],
            "is_bankrupt": result["is_bankrupt"],
        }
    except Exception:
        return {"balance": 0, "is_bankrupt": True}
    finally:
        db.close()


async def process_pause_negotiation(event_text: str) -> str:
    """Gateway-local mock E API: pause negotiation decision."""
    await asyncio.sleep(0)
    return "approved" if "暂停" in event_text else "rejected"


def _authenticate_ws_token(token: str | None) -> int | None:
    """Validate a JWT token and return user_id, or None if invalid."""
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket hub endpoint with JWT auth and reconnection-aware per-user session state."""
    token = ws.query_params.get("token")
    user_id_int = _authenticate_ws_token(token)
    if user_id_int is None:
        await ws.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required"
        )
        return
    user_id = str(user_id_int)

    session = await manager.connect(user_id, ws)
    requested_character_id = (
        str(ws.query_params.get("characterId") or "").strip().lower()
    )
    if requested_character_id in CHARACTER_CATALOG:
        session.character_id = requested_character_id
    session.total_focus_seconds = session.total_focus_seconds or DEFAULT_TOTAL_SECONDS
    session.focus_time_remaining = (
        session.focus_time_remaining
        if session.focus_time_remaining is not None
        else session.total_focus_seconds
    )
    await apply_balance_gate(user_id, session)
    await _hydrate_session_plan(user_id, session)
    await _hydrate_chat_history(user_id, session)

    task = watchdog_tasks.get(user_id)
    if task is None or task.done():
        watchdog_tasks[user_id] = asyncio.create_task(run_watchdog(user_id))

    await send_model_info(user_id, session)
    await send_supervision_state(user_id, session)
    await send_timer_sync(user_id, session)
    if session.current_plan_data is not None:
        await send_plan_update(user_id, session.current_plan_data)
    if session.is_bankrupt:
        await send_control(user_id, "downgrade")

    try:
        while True:
            try:
                message = await ws.receive_json()
            except RuntimeError as exc:
                logger.info(
                    "WebSocket receive ended, user_id=%s error=%s", user_id, exc
                )
                break
            asyncio.create_task(dispatch_message(user_id, session, message))
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected, user_id=%s", user_id)
    finally:
        disconnected_current = manager.disconnect(user_id, ws)
        if disconnected_current:
            audio_buffers.pop(user_id, None)


async def dispatch_message(
    user_id: str, session: SessionState, msg: dict[str, Any]
) -> None:
    """Route frontend messages by protocol type from backend-interface.md."""
    logger.info("ws rx user_id=%s payload=%s", user_id, _summarize_payload(msg))
    msg_type = msg.get("type")

    if msg_type == "text-input":
        await handle_text(user_id, session, msg)
        return

    if msg_type == "periodic-screenshot":
        await handle_screenshot(user_id, session, msg)
        return

    if msg_type == "mic-audio-data":
        await handle_mic_audio_data(user_id, msg)
        return

    if msg_type == "mic-audio-end":
        await handle_mic_audio_end(user_id, session, msg)
        return

    if msg_type == "interrupt-signal":
        logger.info(
            "interrupt-signal received, user_id=%s text=%s",
            user_id,
            msg.get("text", ""),
        )
        audio_buffers.pop(user_id, None)
        return

    if msg_type == "frontend-playback-complete":
        return

    if msg_type == "capture-context-result":
        await handle_capture_context_result(user_id, session, msg)
        return

    if msg_type == "set-locale":
        locale = str(msg.get("locale", "")).strip().lower()
        if locale in {"zh", "en"}:
            session.language_mode = locale
        return

    if msg_type == "set-character":
        character_id = str(msg.get("characterId", "")).strip().lower()
        if character_id in CHARACTER_CATALOG:
            if session.character_id == character_id:
                return
            session.character_id = character_id
            session.chat_history = []
            await send_model_info(user_id, session)
            await send_control(
                user_id,
                "chat-cleared",
                {"reason": "character_switched", "characterId": character_id},
            )
        return

    if msg_type == "resume-now":
        if session.supervision_state == "paused":
            await handle_resume(user_id, session)
            phase_text = await stream_agent_reply(
                user_id=user_id,
                user_text="[SYSTEM_RESULT: RESUME_APPROVED]",
                images=[],
                current_task=session.current_plan,
                language_mode=session.language_mode,
                character_id=session.character_id,
                include_audio=not session.is_bankrupt,
            )
            await _append_chat(session, user_id, "assistant", phase_text)
        return

    if msg_type == "ping":
        await send_control(user_id, "pong")
        return

    logger.warning("Unknown message type: %s", msg_type)


async def handle_mic_audio_data(user_id: str, msg: dict[str, Any]) -> None:
    """Buffer frontend audio samples until mic-audio-end arrives."""
    samples = msg.get("audio", [])
    if not isinstance(samples, list):
        return
    bucket = audio_buffers.setdefault(user_id, [])
    bucket.extend(float(item) for item in samples if isinstance(item, (int, float)))


async def handle_mic_audio_end(
    user_id: str, session: SessionState, msg: dict[str, Any]
) -> None:
    """Call E voice pipeline and stream agent text/audio packets to frontend."""
    if session.is_bankrupt:
        await send_control(user_id, "downgrade")
        await send_agent_text_chunk(user_id, "余额不足，当前仅保留基础文本提示。")
        await send_agent_text_end(user_id)
        return

    audio_samples = audio_buffers.pop(user_id, [])
    images = msg.get("images", [])
    logger.info(
        "mic-audio-end received, user_id=%s samples=%s", user_id, len(audio_samples)
    )
    user_text = await transcribe_audio(audio_samples)
    if not user_text:
        logger.info("ignoring empty ASR transcript as noise, user_id=%s", user_id)
        return

    logger.info("ASR transcript generated, user_id=%s text=%s", user_id, user_text)
    await _handle_user_turn(
        user_id=user_id,
        session=session,
        text=user_text,
        images=images,
        is_tool_result=False,
        emit_user_transcript=True,
    )


async def handle_text(user_id: str, session: SessionState, msg: dict[str, Any]) -> None:
    """Handle text-input by routing through the shared two-phase agent flow."""
    text = str(msg.get("text", ""))
    images = msg.get("images", [])
    is_tool_result = bool(msg.get("tool_result"))
    await _handle_user_turn(
        user_id=user_id,
        session=session,
        text=text,
        images=images,
        is_tool_result=is_tool_result,
        emit_user_transcript=False,
    )


async def _handle_user_turn(
    user_id: str,
    session: SessionState,
    text: str,
    images: list[dict[str, Any]] | None,
    is_tool_result: bool,
    append_user_message: bool = True,
    emit_user_transcript: bool = False,
    stage_depth: int = 0,
) -> None:
    """Run one user turn through white-brain-first and optional system-agent follow-up.

    Phase 1: stream white brain reply while detecting <<SYS>> marker.
    If no <<SYS>>: done (simple chat).
    If <<SYS>> detected:
      - Call system agent for structured directive
      - Execute directive (start/pause/resume/complete/plan/visual-capture)
      - Phase 2: call white brain again with [SYSTEM_RESULT: ...] context
    """
    logger.info("text-input received, user_id=%s text=%s", user_id, text)

    if stage_depth >= MAX_AGENT_STAGES:
        logger.warning(
            "agent stage limit reached, user_id=%s text=%s",
            user_id,
            _truncate_log_text(text),
        )
        await send_tool_call_status(
            user_id, "orchestration", "error", "stage limit reached"
        )
        return

    if emit_user_transcript:
        await send_user_transcript(user_id, text)

    if append_user_message:
        await _append_chat(session, user_id, "user", text)

    async def _run_system_agent() -> Any:
        await send_tool_call_status(
            user_id, "system.agent", "calling", "processing system request"
        )
        return await system_agent.build_directive(user_id, text, session)

    # Phase 1: stream white brain, detect <<SYS>> trigger
    phase1_text, sys_detected, capture_detected, directive_task = await _stream_and_detect_sys(
        user_id=user_id,
        user_text=text,
        images=images,
        current_task=session.current_plan,
        language_mode=session.language_mode,
        character_id=session.character_id,
        include_audio=not session.is_bankrupt,
        on_sys_detected=_run_system_agent,
    )

    if capture_detected:
        await _append_chat(session, user_id, "assistant", phase1_text)
        request_id = uuid.uuid4().hex
        session.set_pending_capture(
            request_id, text, START_CAPTURE_SOURCES, mode="chat"
        )
        await send_tool_call_status(
            user_id, "visual.capture", "calling", "direct visual request"
        )
        await send_control(
            user_id,
            "request-visual-context",
            {"requestId": request_id, "prompt": text, "sources": START_CAPTURE_SOURCES},
        )
        return

    if not sys_detected:
        await _append_chat(session, user_id, "assistant", phase1_text)
        return

    logger.info(
        "phase1 handoff accepted, user_id=%s assistant_text=%s",
        user_id,
        _truncate_log_text(phase1_text),
    )

    # <<SYS>> detected — invoke system agent for structured directive
    directive = await (directive_task or asyncio.create_task(_run_system_agent()))
    if directive.error_message:
        await send_tool_call_status(
            user_id, "system.agent", "error", directive.error_message
        )
        await _handle_user_turn(
            user_id=user_id,
            session=session,
            text=f"{text}\n[SYSTEM_RESULT: SYSTEM_AGENT_ERROR, DETAIL: {_truncate_log_text(directive.error_message)}]",
            images=images,
            is_tool_result=True,
            append_user_message=False,
            emit_user_transcript=False,
            stage_depth=stage_depth + 1,
        )
        return
    await send_tool_call_status(
        user_id, "system.agent", "success", f"action={directive.action}"
    )
    system_events = _normalize_system_events(list(directive.system_events))

    # Handle visual capture request
    if directive.requires_capture:
        if _has_system_result(system_events, "profile_incomplete"):
            # Profile completion has higher priority than visual checks.
            directive.requires_capture = False

        capture_sources = directive.capture_sources or START_CAPTURE_SOURCES
        needs_start_readiness = directive.action == "start" or _has_system_result(
            system_events, "START_ENV_CHECK_REQUIRED"
        )

        if needs_start_readiness and images and session.supervision_state == "setup":
            profile_ready = await _is_profile_ready_for_start(user_id)
            if not profile_ready:
                await send_tool_call_status(
                    user_id, "supervision.start", "error", "profile incomplete"
                )
                system_events = [
                    "[SYSTEM_RESULT: START_REJECTED, CODE: profile_incomplete, DETAIL: 请先轻松聊聊你的称呼和教育背景]"
                ]
            elif not _can_start_session(session):
                await send_tool_call_status(
                    user_id, "supervision.start", "error", "task not agreed"
                )
                system_events = [
                    "[SYSTEM_RESULT: START_REJECTED, CODE: task_not_agreed]"
                ]
            else:
                readiness = await evaluate_start_readiness(
                    images=images,
                    current_task=session.current_plan,
                    session_id=user_id,
                )
                if not readiness.get("approved"):
                    await send_tool_call_status(
                        user_id,
                        "supervision.start",
                        "error",
                        "environment check failed",
                    )
                    system_events = [
                        f"[SYSTEM_RESULT: START_REJECTED, CODE: environment_check_failed, DETAIL: {readiness.get('reason') or '机位或全屏共享不满足要求'}]"
                    ]
                else:
                    duration_seconds = (
                        directive.duration_seconds
                        or session.suggested_focus_seconds
                        or DEFAULT_TOTAL_SECONDS
                    )
                    start_result = await handle_start(
                        user_id, session, duration_seconds=duration_seconds
                    )
                    system_events = _build_start_outcome_system_events(
                        start_result, duration_seconds
                    )

        elif not images and not is_tool_result:
            request_id = uuid.uuid4().hex
            capture_mode = (
                "start-readiness" if needs_start_readiness else "system-agent"
            )
            if directive.action == "start" and directive.duration_seconds:
                session.suggested_focus_seconds = directive.duration_seconds
            session.set_pending_capture(
                request_id, text, capture_sources, mode=capture_mode
            )
            await send_tool_call_status(
                user_id, "visual.capture", "calling", "capturing visual context"
            )
            await send_control(
                user_id,
                "request-visual-context",
                {
                    "requestId": request_id,
                    "prompt": text,
                    "sources": capture_sources,
                },
            )
            return

    # Execute directive actions
    if directive.action == "complete" and session.supervision_state in {
        "active",
        "paused",
    }:
        await handle_complete(user_id, session)

    elif directive.action == "plan" and directive.plan is not None:
        await send_tool_call_status(user_id, "plan.update", "calling", "updating plan")
        persisted_plan = await _persist_active_plan(user_id, directive.plan)
        session.current_plan_data = (persisted_plan or {}).get("plan") or directive.plan
        plan_title = _first_task_title(session.current_plan_data)
        if plan_title:
            session.current_plan = plan_title
        session.suggested_focus_seconds = (
            _plan_focus_seconds(session.current_plan_data) or DEFAULT_TOTAL_SECONDS
        )
        if session.current_plan_data is not None:
            await send_plan_update(user_id, session.current_plan_data)
        await send_tool_call_status(user_id, "plan.update", "success", "plan updated")

    elif directive.action == "start" and session.supervision_state == "setup":
        profile_ready = await _is_profile_ready_for_start(user_id)
        if not profile_ready:
            await send_tool_call_status(
                user_id, "supervision.start", "error", "profile incomplete"
            )
            system_events = [
                "[SYSTEM_RESULT: START_REJECTED, CODE: profile_incomplete, DETAIL: 请先轻松聊聊你的称呼和教育背景]"
            ]
        elif not _can_start_session(session):
            await send_tool_call_status(
                user_id, "supervision.start", "error", "task not agreed"
            )
            system_events = ["[SYSTEM_RESULT: START_REJECTED, CODE: task_not_agreed]"]
        elif not images:
            request_id = uuid.uuid4().hex
            duration_seconds = (
                directive.duration_seconds
                or session.suggested_focus_seconds
                or DEFAULT_TOTAL_SECONDS
            )
            session.suggested_focus_seconds = duration_seconds
            session.set_pending_capture(
                request_id, text, START_CAPTURE_SOURCES, mode="start-readiness"
            )
            await send_tool_call_status(
                user_id,
                "visual.capture",
                "calling",
                "checking camera and full-screen share before start",
            )
            await send_control(
                user_id,
                "request-visual-context",
                {
                    "requestId": request_id,
                    "prompt": text,
                    "sources": START_CAPTURE_SOURCES,
                },
            )
            return
        else:
            readiness = await evaluate_start_readiness(
                images=images,
                current_task=session.current_plan,
                session_id=user_id,
            )
            if not readiness.get("approved"):
                await send_tool_call_status(
                    user_id, "supervision.start", "error", "environment check failed"
                )
                system_events = [
                    f"[SYSTEM_RESULT: START_REJECTED, CODE: environment_check_failed, DETAIL: {readiness.get('reason') or '机位或全屏共享不满足要求'}]"
                ]
            else:
                duration_seconds = (
                    directive.duration_seconds
                    or session.suggested_focus_seconds
                    or DEFAULT_TOTAL_SECONDS
                )
                start_result = await handle_start(
                    user_id, session, duration_seconds=duration_seconds
                )
                system_events = _build_start_outcome_system_events(
                    start_result, duration_seconds
                )

    elif directive.action == "pause" and session.supervision_state == "active":
        session.pause_requests_count += 1
        if directive.approved:
            await handle_pause(
                user_id, session, pause_seconds=directive.pause_seconds or 300
            )
            await _record_pause_request(
                user_id,
                session,
                requested_text=text,
                approved=True,
                pause_seconds=directive.pause_seconds or 300,
                decision_reason="approved by system agent",
            )
        else:
            await send_tool_call_status(
                user_id, "supervision.pause", "error", "pause rejected"
            )
            await _record_pause_request(
                user_id,
                session,
                requested_text=text,
                approved=False,
                pause_seconds=None,
                decision_reason="pause rejected",
            )
            system_events = _normalize_system_events(
                _build_fallback_system_events(
                    directive,
                    session,
                    {"reason": "此次暂停审核未通过"},
                )
            )

    elif directive.action == "resume" and session.supervision_state == "paused":
        await handle_resume(user_id, session)
        system_events = _normalize_system_events(
            _build_fallback_system_events(directive, session)
        )

    if session.is_bankrupt and directive.action != "complete":
        await send_control(user_id, "downgrade")
        system_events.append("[SYSTEM_EVENT: DEGRADE_MODE_ACTIVE]")

    if not system_events:
        system_events = _normalize_system_events(
            _build_fallback_system_events(directive, session)
        )

    # Continue the turn with system results. The white brain may decide to stop
    # here or emit <<SYS>> again for another system round.
    result_context = (
        "\n".join(system_events)
        if system_events
        else f"[SYSTEM_RESULT: action={directive.action}, approved={directive.approved}]"
    )
    enriched_text = f"{text}\n{result_context}"
    logger.info(
        "follow-up request, user_id=%s stage=%s action=%s result_context=%s",
        user_id,
        stage_depth + 1,
        directive.action,
        _truncate_log_text(result_context),
    )
    await _handle_user_turn(
        user_id=user_id,
        session=session,
        text=enriched_text,
        images=images,
        is_tool_result=True,
        append_user_message=False,
        emit_user_transcript=False,
        stage_depth=stage_depth + 1,
    )


async def handle_capture_context_result(
    user_id: str,
    session: SessionState,
    msg: dict[str, Any],
) -> None:
    """Resume one chat turn after frontend capture tool returns images."""
    images = msg.get("images", [])
    error = str(msg.get("error", "")).strip()
    request_id = str(msg.get("requestId", "")).strip()
    if not request_id or request_id != session.pending_capture_request_id:
        await send_tool_call_status(
            user_id, "visual.capture", "error", "unknown or expired requestId"
        )
        return

    prompt = str(msg.get("prompt", "")).strip() or (
        session.pending_capture_prompt or ""
    )
    capture_mode = session.pending_capture_mode
    session.clear_pending_capture()
    if error or not images:
        await send_tool_call_status(
            user_id, "visual.capture", "error", error or "no images captured"
        )
        await _handle_user_turn(
            user_id=user_id,
            session=session,
            text=(
                f"{prompt}\n[SYSTEM_EVENT: VISUAL_CONTEXT_CAPTURE_FAILED]"
                if prompt
                else "[SYSTEM_EVENT: VISUAL_CONTEXT_CAPTURE_FAILED]"
            ),
            images=[],
            is_tool_result=True,
            append_user_message=False,
            emit_user_transcript=False,
            stage_depth=1,
        )
        return

    await send_tool_call_status(
        user_id, "visual.capture", "success", "visual context captured"
    )
    if capture_mode == "start-readiness":
        profile_ready = await _is_profile_ready_for_start(user_id)
        if not profile_ready:
            await send_tool_call_status(
                user_id, "supervision.start", "error", "profile incomplete"
            )
            system_events = [
                "[SYSTEM_RESULT: START_REJECTED, CODE: profile_incomplete, DETAIL: 请先轻松聊聊你的称呼和教育背景]"
            ]
            result_context = "\n".join(system_events)
            await _handle_user_turn(
                user_id=user_id,
                session=session,
                text=f"{prompt}\n{result_context}",
                images=images,
                is_tool_result=True,
                append_user_message=False,
                emit_user_transcript=False,
                stage_depth=1,
            )
            return

        readiness = await evaluate_start_readiness(
            images=images,
            current_task=session.current_plan,
            session_id=user_id,
        )
        if readiness.get("approved"):
            duration_seconds = session.suggested_focus_seconds or DEFAULT_TOTAL_SECONDS
            start_result = await handle_start(
                user_id, session, duration_seconds=duration_seconds
            )
            system_events = _build_start_outcome_system_events(
                start_result, duration_seconds
            )
        else:
            await send_tool_call_status(
                user_id, "supervision.start", "error", "environment check failed"
            )
            system_events = [
                f"[SYSTEM_RESULT: START_REJECTED, CODE: environment_check_failed, DETAIL: {readiness.get('reason') or '机位或全屏共享不满足要求'}]"
            ]

        result_context = "\n".join(system_events)
        await _handle_user_turn(
            user_id=user_id,
            session=session,
            text=f"{prompt}\n{result_context}",
            images=images,
            is_tool_result=True,
            append_user_message=False,
            emit_user_transcript=False,
            stage_depth=1,
        )
        return

    await _handle_user_turn(
        user_id=user_id,
        session=session,
        text=prompt,
        images=images,
        is_tool_result=True,
        append_user_message=False,
        emit_user_transcript=False,
    )


def _build_temporal_stitched_image(
    session: SessionState, current_images: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    import time
    import io
    import base64
    from PIL import Image, ImageDraw, ImageFont

    now = time.time()
    session.image_timeline.append((now, current_images))
    session.image_timeline = [
        item for item in session.image_timeline if now - item[0] < 400
    ]

    targets = [0, 5, 10, 30, 60, 120]
    selected = []
    seen_ids = set()

    for t_offset in targets:
        target_time = now - t_offset
        if not session.image_timeline:
            break
        closest = min(session.image_timeline, key=lambda x: abs(x[0] - target_time))
        # only include if not chosen before
        item_id = id(closest[1])
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            selected.append(closest)

    selected.sort(key=lambda x: x[0], reverse=True)
    ROW_HEIGHT = 240
    row_images = []

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for timestamp, imgs in selected:
        pil_imgs = []
        for img_dict in imgs:
            b64 = str(img_dict.get("data", ""))
            if not b64:
                continue
            try:
                img_data = base64.b64decode(b64)
                pil_imgs.append(Image.open(io.BytesIO(img_data)).convert("RGB"))
            except Exception:
                pass

        if not pil_imgs:
            continue

        scaled_imgs = []
        total_w = 0
        for pimg in pil_imgs:
            w, h = pimg.size
            new_w = int(w * (ROW_HEIGHT / h))
            scaled = pimg.resize((new_w, ROW_HEIGHT), Image.Resampling.LANCZOS)
            scaled_imgs.append(scaled)
            total_w += new_w

        group_img = Image.new("RGB", (total_w, ROW_HEIGHT))
        x_offset = 0
        for sc in scaled_imgs:
            group_img.paste(sc, (x_offset, 0))
            x_offset += sc.width

        dt = int(now - timestamp)
        label = "T" if dt <= 1 else f"T-{dt}s"
        txt_height = 24

        row_final = Image.new(
            "RGB", (group_img.width, group_img.height + txt_height), color=(30, 30, 30)
        )
        row_final.paste(group_img, (0, txt_height))
        draw = ImageDraw.Draw(row_final)
        draw.text((5, 2), label, fill=(255, 255, 0), font=font)
        row_images.append(row_final)

    if not row_images:
        return current_images

    final_w = max(r.width for r in row_images)
    final_h = sum(r.height for r in row_images)

    final_img = Image.new("RGB", (final_w, final_h), color=(0, 0, 0))
    y_offset = 0
    for r in row_images:
        final_img.paste(r, (0, y_offset))
        y_offset += r.height

    buf = io.BytesIO()
    final_img.save(buf, format="JPEG", quality=75)
    final_b64 = base64.b64encode(buf.getvalue()).decode()

    return [
        {
            "source": "temporal_stitched",
            "hint": "Stitched sparse time series image",
            "data": final_b64,
        }
    ]


async def handle_screenshot(
    user_id: str, session: SessionState, msg: dict[str, Any]
) -> None:
    """Call E vision judgement and C penalty API with threshold arbitration."""
    if session.is_bankrupt:
        return

    images = msg.get("images", [])

    if images:
        images_for_vision = _build_temporal_stitched_image(session, images)
    else:
        images_for_vision = []

    is_distracted, reason = await evaluate_vision(
        images_for_vision,
        current_task=session.current_plan,
        session_id=user_id,
    )

    if not is_distracted:
        session.distraction_streak = 0
        return

    session.distraction_streak += 1

    # 附加上 reason 帮助聊天模型给出具体提醒
    reason_str = f"走神原因: {reason}。" if reason else ""

    if session.distraction_streak < DISTRACTION_THRESHOLD:
        await send_supervision_alert(
            user_id,
            message="检测到注意力波动，请回到当前任务。",
            severity="soft",
            streak_count=session.distraction_streak,
        )
        prompt_text = (
            f"系统自动检测到用户走神了（{reason_str}），请根据以下事件使用严厉的语气结合检测到的原因去催促用户回到学习，要求极短。\n"
            f"[SYSTEM_EVENT: DISTRACTION_WARNING, STREAK: {session.distraction_streak}]"
        )
        await _handle_user_turn(
            user_id=user_id,
            session=session,
            text=prompt_text,
            images=[],
            is_tool_result=True,
            append_user_message=False,
            emit_user_transcript=False,
            stage_depth=1,
        )
        return

    result = await deduct_penalty(user_id, amount=PENALTY_AMOUNT)
    balance = int(result.get("balance", 0))
    is_bankrupt = bool(result.get("is_bankrupt", balance <= 0))
    session.is_bankrupt = is_bankrupt

    await send_balance_update(
        user_id,
        balance=balance,
        change=-PENALTY_AMOUNT,
        reason="检测到连续走神",
    )

    if is_bankrupt:
        await send_supervision_alert(
            user_id,
            message="余额不足，已切换为降级模式。",
            severity="hard",
            streak_count=session.distraction_streak,
        )
        await send_control(user_id, "downgrade")
    else:
        prompt_text = (
            f"系统自动执行了走神惩罚（{reason_str}），请根据以下事件严厉警告用户，要求极短。\n"
            f"[SYSTEM_EVENT: DISTRACTION_PENALTY_APPLIED, AMOUNT_RMB: {_format_rmb_from_cents(PENALTY_AMOUNT)}]"
        )
        await _handle_user_turn(
            user_id=user_id,
            session=session,
            text=prompt_text,
            images=images,
            is_tool_result=True,
            append_user_message=False,
            emit_user_transcript=False,
            stage_depth=1,
        )

    session.distraction_streak = 0


async def run_watchdog(user_id: str) -> None:
    """Per-user background timer that updates countdown without blocking WS loop."""
    while True:
        await asyncio.sleep(1)
        manager.cleanup_expired_states()
        session = manager.user_states.get(user_id)
        if session is None:
            return

        if session.supervision_state == "active" and not session.is_bankrupt:
            is_timeout = session.tick()
            await send_timer_sync(user_id, session)
            if is_timeout:
                await handle_complete(user_id, session)
                return

        if session.supervision_state == "paused":
            pause_timeout = session.tick_pause()
            if pause_timeout:
                await handle_resume(user_id, session)


async def apply_balance_gate(user_id: str, session: SessionState) -> None:
    """Handshake interception: query balance from C and set downgrade flag."""
    result = await get_user_balance(user_id)
    balance = int(result.get("balance", 0))
    session.is_bankrupt = bool(result.get("is_bankrupt", balance <= 0))


async def handle_start(
    user_id: str, session: SessionState, duration_seconds: int
) -> dict[str, Any] | None:
    """Start supervision and publish state/timer changes."""
    await send_tool_call_status(
        user_id, "supervision.start", "calling", "starting supervision"
    )
    try:
        db = SessionLocal()
        try:
            result = db_start_focus_session(
                db=db,
                user_id=int(user_id),
                planned_focus_minutes=max(duration_seconds // 60, 1),
            )
        finally:
            db.close()

        session.start(duration_seconds=duration_seconds)
        session.suggested_focus_seconds = duration_seconds
        await send_supervision_state(user_id, session, reason="approved start")
        await send_timer_sync(user_id, session)
        await send_balance_update(
            user_id,
            balance=int(result["balance_after"]),
            change=-int(result["upfront_cost"]),
            reason="开始专注，已预扣服务费",
        )
        session.session_ref = str(result.get("session_ref") or "") or None
        await send_tool_call_status(
            user_id, "supervision.start", "success", "supervision started"
        )
        return {"ok": True, **result}
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.start", "error", str(exc))
        return {"ok": False, "error": str(exc)}


async def handle_pause(user_id: str, session: SessionState, pause_seconds: int) -> None:
    """Pause supervision and emit updated pause metadata."""
    await send_tool_call_status(
        user_id, "supervision.pause", "calling", "pausing supervision"
    )
    try:
        session.pause(duration_seconds=pause_seconds)
        await send_supervision_state(user_id, session, reason="approved pause")
        await send_tool_call_status(
            user_id, "supervision.pause", "success", "supervision paused"
        )
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.pause", "error", str(exc))


async def handle_resume(user_id: str, session: SessionState) -> None:
    """Resume supervision after pause and sync state."""
    await send_tool_call_status(
        user_id, "supervision.resume", "calling", "resuming supervision"
    )
    try:
        session.resume()
        await send_supervision_state(user_id, session, reason="approved resume")
        await send_tool_call_status(
            user_id, "supervision.resume", "success", "supervision resumed"
        )
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.resume", "error", str(exc))


async def handle_complete(user_id: str, session: SessionState) -> None:
    """Complete supervision when timer reaches zero."""
    await send_tool_call_status(
        user_id, "supervision.complete", "calling", "completing session"
    )
    try:
        summary_snapshot = SessionState(
            supervision_state=session.supervision_state,
            start_time=session.start_time,
            focus_time_remaining=session.focus_time_remaining,
            total_focus_seconds=session.total_focus_seconds,
            distraction_streak=session.distraction_streak,
            is_bankrupt=session.is_bankrupt,
            current_plan=session.current_plan,
            current_plan_data=session.current_plan_data,
            session_ref=session.session_ref,
            pause_remaining_seconds=session.pause_remaining_seconds,
            suggested_focus_seconds=session.suggested_focus_seconds,
            pause_requests_count=session.pause_requests_count,
            pending_capture_request_id=session.pending_capture_request_id,
            pending_capture_prompt=session.pending_capture_prompt,
            pending_capture_sources=list(session.pending_capture_sources),
            chat_history=list(session.chat_history),
        )
        session.complete()
        await send_supervision_state(user_id, session, reason="time up")
        await send_timer_sync(user_id, session)
        await send_tool_call_status(
            user_id, "supervision.complete", "success", "session completed"
        )
        await _persist_session_summary(user_id, summary_snapshot)
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.complete", "error", str(exc))


async def stream_agent_reply(
    user_id: str,
    user_text: str,
    images: list[dict[str, Any]] | None,
    current_task: str | None,
    language_mode: str,
    character_id: str,
    include_audio: bool,
) -> str:
    """Stream one white-brain reply; optionally suppress audio in degraded mode.

    Returns the collected reply text.
    """
    parts: list[str] = []
    sent_text = False
    audio_tasks = []
    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=user_id,
        images=images,
        current_task=current_task,
        language_mode=language_mode,
        character_id=character_id,
    ):
        chunk_text = _sanitize_agent_text(str(chunk.get("text", "")))
        expression = str(chunk.get("expression", "neutral"))
        audio_coro = chunk.get("audio_coro")
        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            await send_agent_text_chunk(user_id, chunk_text)
        if include_audio and audio_coro is not None and chunk_text:
            audio_task = asyncio.create_task(audio_coro)
            audio_tasks.append((audio_task, expression, chunk_text))

    for task, expression, chunk_text in audio_tasks:
        try:
            audio_data = await task
            if audio_data:
                await send_audio(
                    user_id,
                    audio=audio_data,
                    expression=expression,
                    text=chunk_text or "...",
                )
        except Exception:
            logger.exception("Failed to generate audio for chunk")

    if sent_text:
        await send_agent_text_end(user_id)
        return "".join(parts)

    logger.warning(
        "empty white-brain reply, user_id=%s text=%s",
        user_id,
        _truncate_log_text(user_text),
    )
    await send_agent_text_end(user_id)
    return ""


async def _stream_and_detect_sys(
    user_id: str,
    user_text: str,
    images: list[dict[str, Any]] | None,
    current_task: str | None,
    language_mode: str,
    character_id: str,
    include_audio: bool,
    on_sys_detected: Callable[[], Coroutine[Any, Any, Any]] | None = None,
) -> tuple[str, bool, bool, asyncio.Task[Any] | None]:
    """Stream white-brain reply while detecting the <<SYS>> and <<CAPTURE>> trigger markers.

    Returns (collected_clean_text, sys_detected, capture_detected, directive_task).
    """
    parts: list[str] = []
    sys_detected = False
    capture_detected = False
    sent_text = False
    sys_task: asyncio.Task[Any] | None = None

    audio_tasks = []

    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=user_id,
        images=images,
        current_task=current_task,
        language_mode=language_mode,
        character_id=character_id,
    ):
        chunk_text = _sanitize_agent_text(str(chunk.get("text", "")))
        expression = str(chunk.get("expression", "neutral"))
        audio_coro = chunk.get("audio_coro")
        chunk_sys_triggered = bool(chunk.get("sys_triggered"))
        chunk_capture_triggered = bool(chunk.get("capture_triggered"))

        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            await send_agent_text_chunk(user_id, chunk_text)

        if chunk_capture_triggered and not capture_detected:
            capture_detected = True
            logger.info("CAPTURE trigger detected for user_id=%s", user_id)

        if chunk_sys_triggered and not sys_detected and not chunk_capture_triggered:
            sys_detected = True
            logger.info("SYS trigger detected for user_id=%s", user_id)
            if on_sys_detected is not None:
                sys_task = asyncio.create_task(on_sys_detected())

        if include_audio and audio_coro is not None and chunk_text:
            # We wrap the audio coroutine into a task to run it concurrently,
            # and append it to our queue of audio tasks.
            audio_task = asyncio.create_task(audio_coro)
            audio_tasks.append((audio_task, expression, chunk_text))

    # Await and send audio chunks in order, but in the background relative to text streaming
    for task, expression, chunk_text in audio_tasks:
        try:
            audio_data = await task
            if audio_data:
                await send_audio(
                    user_id,
                    audio=audio_data,
                    expression=expression,
                    text=chunk_text,
                )
        except Exception:
            logger.exception("Failed to generate audio for chunk")

    if sent_text:
        await send_agent_text_end(user_id)
    elif not sys_detected and not capture_detected:
        logger.warning(
            "empty phase1 reply without SYS or CAPTURE, user_id=%s text=%s",
            user_id,
            _truncate_log_text(user_text),
        )
        await send_agent_text_end(user_id)

    return "".join(parts), sys_detected, capture_detected, sys_task



def _resolve_character(session: SessionState) -> tuple[str, dict[str, Any]]:
    character_id = (
        session.character_id
        if session.character_id in CHARACTER_CATALOG
        else DEFAULT_CHARACTER_ID
    )
    return character_id, CHARACTER_CATALOG[character_id]


async def send_model_info(user_id: str, session: SessionState) -> None:
    """Send Live2D model configuration payload."""
    character_id, character = _resolve_character(session)
    await manager.send_personal_message(
        user_id,
        {
            "type": "model-info",
            "character_id": character_id,
            "character": {
                "name": character.get("name"),
                "displayName": character.get("displayName"),
                "description": character.get("description"),
                "languageHints": character.get("languageHints", []),
                "personaStyle": character.get("personaStyle"),
            },
            "model_info": character.get("modelInfo", {}),
        },
    )


async def send_supervision_state(
    user_id: str, session: SessionState, reason: str | None = None
) -> None:
    """Send supervision-state-change with optional metadata fields."""
    payload: dict[str, Any] = {
        "type": "supervision-state-change",
        "state": session.supervision_state,
    }
    if session.total_focus_seconds is not None:
        payload["duration"] = session.total_focus_seconds
    if session.current_plan:
        payload["task"] = session.current_plan
    if session.pause_remaining_seconds is not None:
        payload["pauseDuration"] = session.pause_remaining_seconds
    if reason:
        payload["reason"] = reason
    await manager.send_personal_message(user_id, payload)


async def send_timer_sync(user_id: str, session: SessionState) -> None:
    """Push timer-sync packet to keep frontend countdown aligned."""
    remaining_seconds = (
        session.focus_time_remaining
        if session.focus_time_remaining is not None
        else (session.total_focus_seconds or DEFAULT_TOTAL_SECONDS)
    )
    total_seconds = session.total_focus_seconds or DEFAULT_TOTAL_SECONDS
    await manager.send_personal_message(
        user_id,
        {
            "type": "timer-sync",
            "remainingSeconds": remaining_seconds,
            "totalSeconds": total_seconds,
        },
    )


async def send_agent_text_chunk(user_id: str, text: str) -> None:
    """Send one agent text streaming chunk."""
    clean_text = _sanitize_agent_text(text)
    if not clean_text:
        return
    await manager.send_personal_message(
        user_id,
        {
            "type": "agent-text-chunk",
            "text": clean_text,
        },
    )


async def send_user_transcript(user_id: str, text: str) -> None:
    """Send the finalized ASR transcript so frontend can render it as a user turn."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "user-transcript",
            "text": text,
        },
    )


async def send_agent_text_end(user_id: str) -> None:
    """Mark the end of one agent text streaming turn."""
    await manager.send_personal_message(user_id, {"type": "agent-text-end"})


async def send_audio(user_id: str, audio: str, expression: str, text: str) -> None:
    """Send audio packet in frontend contract shape."""
    clean_text = _sanitize_agent_text(text) or "..."
    await manager.send_personal_message(
        user_id,
        {
            "type": "audio",
            "audio": audio,
            "actions": {"expressions": [expression]},
            "display_text": {"text": clean_text, "name": BOT_NAME},
        },
    )


async def send_supervision_alert(
    user_id: str, message: str, severity: str, streak_count: int
) -> None:
    """Send supervision-alert message."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "supervision-alert",
            "message": message,
            "severity": severity,
            "streakCount": streak_count,
        },
    )


async def send_tool_call_status(
    user_id: str, tool: str, status: str, message: str
) -> None:
    """Emit tool-call-status lifecycle event."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "tool-call-status",
            "tool": tool,
            "status": status,
            "message": message,
        },
    )


async def send_plan_update(user_id: str, plan: dict[str, Any]) -> None:
    """Emit plan-update event."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "plan-update",
            "plan": plan,
        },
    )


async def send_balance_update(
    user_id: str, balance: int, change: int, reason: str
) -> None:
    """Emit balance-update event."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "balance-update",
            "balance": balance,
            "change": change,
            "reason": reason,
        },
    )


async def send_control(
    user_id: str, command: str, payload: dict[str, Any] | None = None
) -> None:
    """Emit control command message to frontend."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "control",
            "command": command,
            "payload": payload or {},
        },
    )
