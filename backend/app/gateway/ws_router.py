from __future__ import annotations

import asyncio
import json
import uuid
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth.security import decode_access_token
from app.business.models import SessionLocal
from app.business.crud import (
    PENALTY_PER_DISTRACTION,
    create_session_summary as db_create_session_summary,
    execute_penalty as db_execute_penalty,
    get_active_plan as db_get_active_plan,
    get_user_status as db_get_user_status,
    record_pause_request as db_record_pause_request,
    start_focus_session as db_start_focus_session,
    upsert_study_plan as db_upsert_study_plan,
)
from app.gateway.session import SessionState
from app.media_ai import evaluate_vision, process_text_chat, transcribe_audio
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
            logger.info("flushing queued ws messages user_id=%s count=%s", user_id, len(queued_messages))
            for payload in queued_messages:
                await self.send_personal_message(user_id, payload)
        return session

    def disconnect(self, user_id: str) -> None:
        """Mark one user as disconnected while preserving session for TTL."""
        self.active_connections.pop(user_id, None)
        self.disconnected_at[user_id] = datetime.now(UTC)
        self.cleanup_expired_states()

    async def send_personal_message(self, user_id: str, payload: dict) -> None:
        """Send one message to a specific active user."""
        websocket = self.active_connections.get(user_id)
        if websocket is None:
            logger.warning("ws tx queued user_id=%s reason=no-active-connection payload=%s", user_id, _summarize_payload(payload))
            self.pending_messages.setdefault(user_id, []).append(payload)
            return
        logger.info("ws tx user_id=%s payload=%s", user_id, _summarize_payload(payload))
        try:
            await websocket.send_json(payload)
        except Exception:
            logger.exception("ws tx failed, queueing for retry user_id=%s", user_id)
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

MODEL_INFO = {
    "name": "mao_pro",
    "url": "/live2d-models/mao_pro/mao_pro.model3.json",
    "kScale": 0.5,
    "emotionMap": {
        "happy": 3,
        "neutral": 0,
    },
    "idleMotionGroup": "Idle",
    "talkMotionGroup": "",
}

DEFAULT_TOTAL_SECONDS = 1500
DISTRACTION_THRESHOLD = 3
PENALTY_AMOUNT = PENALTY_PER_DISTRACTION
BOT_NAME = "Study Buddy"
DEFAULT_BALANCE = 100
SYS_MARKER = "<<SYS>>"
LOG_PREVIEW_LIMIT = 240

watchdog_tasks: dict[str, asyncio.Task] = {}
audio_buffers: dict[str, list[float]] = {}
system_agent = SystemAgentService()


def _duration_to_minutes(duration_seconds: int | None) -> int | None:
    if duration_seconds is None:
        return None
    return max(1, duration_seconds // 60)


def _build_fallback_system_events(
    directive: Any,
    session: SessionState,
    extra: dict[str, Any] | None = None,
) -> list[str]:
    if directive.system_events:
        return [str(event) for event in directive.system_events if str(event).strip()]

    details = extra or {}
    if directive.action == "start":
        minutes = details.get("minutes") or _duration_to_minutes(directive.duration_seconds)
        cost = details.get("cost")
        if cost is not None:
            return [f"[SYSTEM_RESULT: SESSION_STARTED, MINUTES: {minutes}, COST: {cost}]"]
        return [f"[SYSTEM_RESULT: SESSION_STARTED, MINUTES: {minutes}]"]
    if directive.action == "pause":
        if directive.approved:
            minutes = details.get("minutes") or _duration_to_minutes(directive.pause_seconds)
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
        return [f"[SYSTEM_RESULT: PLAN_UPDATED, TITLE: {title}, TOTAL_MINUTES: {total_minutes}]"]
    return []


def _first_task_title(plan: dict[str, Any] | None) -> str | None:
    if not plan:
        return None
    tasks = plan.get("tasks") or []
    if not tasks:
        return None
    return str(tasks[0].get("title") or "").strip() or None


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


async def _persist_active_plan(user_id: str, plan: dict[str, Any]) -> dict[str, Any] | None:
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
        suggested_duration = session.current_plan_data.get("suggestedDuration")
        if suggested_duration is not None:
            session.suggested_focus_seconds = int(suggested_duration)


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
    except Exception:
        logger.exception("failed to persist session summary, user_id=%s", user_id)
    finally:
        db.close()


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
    return text.replace(SYS_MARKER, "").strip()


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
            summary[key] = {nested_key: _truncate_log_text(nested_value) for nested_key, nested_value in value.items()}
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


def _assistant_requested_system_action(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False

    handoff_phrases = (
        "我帮你申请",
        "我去替你申请",
        "我替你申请",
        "我帮你安排",
        "我去给你安排",
        "我替你安排",
        "我给你安排",
        "我帮你处理",
        "我去处理",
        "我替你处理",
        "我去替你准备",
        "我替你准备",
        "让我看看",
        "我帮你看看",
        "我去看一眼",
    )
    return any(phrase in cleaned for phrase in handoff_phrases)


def _infer_visual_sources_from_text(text: str) -> list[str]:
    lowered = text.lower()
    wants_screen = any(keyword in text or keyword in lowered for keyword in (
        "桌面", "屏幕", "页面", "窗口", "代码", "文档", "screen", "desktop", "window",
    ))
    wants_camera = any(keyword in text or keyword in lowered for keyword in (
        "摄像头", "镜头", "看到我", "看我", "我吗", "我现在", "camera", "cam", "look at me",
    ))
    generic_visual = any(keyword in text or keyword in lowered for keyword in (
        "看看", "看下", "帮我看", "瞧瞧", "看到", "能看到", "分析一下", "show me", "look",
    ))

    sources: list[str] = []
    if wants_camera:
        sources.append("camera")
    if wants_screen:
        sources.append("screen")
    if not sources and generic_visual:
        sources.append("camera")
    return sources


def _is_direct_visual_chat_request(text: str) -> bool:
    return bool(_infer_visual_sources_from_text(text))


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
            db, uid, reason="检测到连续走神", distraction_count=1, penalty_amount=amount,
        )
        return {"balance": result["balance_after"], "is_bankrupt": result["is_bankrupt"]}
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
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return
    user_id = str(user_id_int)

    session = await manager.connect(user_id, ws)
    session.total_focus_seconds = session.total_focus_seconds or DEFAULT_TOTAL_SECONDS
    session.focus_time_remaining = (
        session.focus_time_remaining
        if session.focus_time_remaining is not None
        else session.total_focus_seconds
    )
    await apply_balance_gate(user_id, session)
    await _hydrate_session_plan(user_id, session)

    task = watchdog_tasks.get(user_id)
    if task is None or task.done():
        watchdog_tasks[user_id] = asyncio.create_task(run_watchdog(user_id))

    await send_model_info(user_id)
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
                logger.info("WebSocket receive ended, user_id=%s error=%s", user_id, exc)
                break
            await dispatch_message(user_id, session, message)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected, user_id=%s", user_id)
    finally:
        manager.disconnect(user_id)
        task = watchdog_tasks.pop(user_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        audio_buffers.pop(user_id, None)


async def dispatch_message(user_id: str, session: SessionState, msg: dict[str, Any]) -> None:
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
        logger.info("interrupt-signal received, user_id=%s text=%s", user_id, msg.get("text", ""))
        audio_buffers.pop(user_id, None)
        return

    if msg_type == "frontend-playback-complete":
        return

    if msg_type == "capture-context-result":
        await handle_capture_context_result(user_id, session, msg)
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
    logger.info("mic-audio-end received, user_id=%s samples=%s", user_id, len(audio_samples))
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

    if emit_user_transcript:
        await send_user_transcript(user_id, text)

    if append_user_message:
        session.append_chat("user", text)

    if not images and not is_tool_result and _is_direct_visual_chat_request(text):
        sources = _infer_visual_sources_from_text(text)
        logger.info(
            "direct visual chat requested, user_id=%s text=%s sources=%s",
            user_id,
            _truncate_log_text(text),
            sources,
        )
        request_id = uuid.uuid4().hex
        session.set_pending_capture(request_id, text, sources, mode="direct-chat")
        await send_tool_call_status(user_id, "visual.capture", "calling", "capturing visual context for chat")
        await send_control(
            user_id,
            "request-visual-context",
            {
                "requestId": request_id,
                "prompt": text,
                "sources": sources,
            },
        )
        return

    # Phase 1: stream white brain, detect <<SYS>> trigger
    phase1_text, sys_detected = await _stream_and_detect_sys(
        user_id=user_id,
        user_text=text,
        images=images,
        current_task=session.current_plan,
        include_audio=not session.is_bankrupt,
    )

    repaired_handoff = False
    if not sys_detected and _assistant_requested_system_action(phase1_text):
        repaired_handoff = True
        sys_detected = True
        logger.warning(
            "repairing missing SYS marker from assistant output, user_id=%s assistant_text=%s",
            user_id,
            _truncate_log_text(phase1_text),
        )

    if not sys_detected:
        session.append_chat("assistant", phase1_text)
        return

    logger.info(
        "phase1 handoff accepted, user_id=%s repaired=%s assistant_text=%s",
        user_id,
        repaired_handoff,
        _truncate_log_text(phase1_text),
    )

    # <<SYS>> detected — invoke system agent for structured directive
    await send_tool_call_status(user_id, "system.agent", "calling", "processing system request")
    directive = await system_agent.build_directive(user_id, text, session)
    if directive.error_message:
        await send_tool_call_status(user_id, "system.agent", "error", directive.error_message)
        fallback_text = "我这边替你提交了，但系统处理超时了。你先别急，我再试一次。"
        await send_agent_text_chunk(user_id, fallback_text)
        await send_agent_text_end(user_id)
        session.append_chat("assistant", fallback_text)
        return
    await send_tool_call_status(user_id, "system.agent", "success", f"action={directive.action}")
    system_events = _normalize_system_events(list(directive.system_events))

    # Handle visual capture request
    if directive.requires_capture and not images and not is_tool_result:
        request_id = uuid.uuid4().hex
        session.set_pending_capture(request_id, text, directive.capture_sources)
        await send_tool_call_status(user_id, "visual.capture", "calling", "capturing visual context")
        await send_control(
            user_id,
            "request-visual-context",
            {
                "requestId": request_id,
                "prompt": text,
                "sources": directive.capture_sources,
            },
        )
        return

    # Execute directive actions
    if directive.action == "complete" and session.supervision_state in {"active", "paused"}:
        await handle_complete(user_id, session)

    elif directive.action == "plan" and directive.plan is not None:
        await send_tool_call_status(user_id, "plan.update", "calling", "updating plan")
        persisted_plan = await _persist_active_plan(user_id, directive.plan)
        session.current_plan_data = (persisted_plan or {}).get("plan") or directive.plan
        plan_title = _first_task_title(session.current_plan_data)
        if plan_title:
            session.current_plan = plan_title
        session.suggested_focus_seconds = int(
            (session.current_plan_data or {}).get("suggestedDuration") or DEFAULT_TOTAL_SECONDS
        )
        await send_plan_update(user_id, session.current_plan_data)
        await send_tool_call_status(user_id, "plan.update", "success", "plan updated")

    elif directive.action == "start" and session.supervision_state == "setup":
        duration_seconds = directive.duration_seconds or session.suggested_focus_seconds or DEFAULT_TOTAL_SECONDS
        start_result = await handle_start(user_id, session, duration_seconds=duration_seconds)
        if start_result:
            system_events = _normalize_system_events(_build_fallback_system_events(
                directive,
                session,
                {
                    "minutes": max(duration_seconds // 60, 1),
                    "cost": start_result.get("upfront_cost"),
                },
            ))

    elif directive.action == "pause" and session.supervision_state == "active":
        session.pause_requests_count += 1
        if directive.approved:
            await handle_pause(user_id, session, pause_seconds=directive.pause_seconds or 300)
            await _record_pause_request(
                user_id,
                session,
                requested_text=text,
                approved=True,
                pause_seconds=directive.pause_seconds or 300,
                decision_reason="approved by system agent",
            )
        else:
            await send_tool_call_status(user_id, "supervision.pause", "error", "pause rejected")
            await _record_pause_request(
                user_id,
                session,
                requested_text=text,
                approved=False,
                pause_seconds=None,
                decision_reason="pause rejected",
            )
            system_events = _normalize_system_events(_build_fallback_system_events(
                directive,
                session,
                {"reason": "此次暂停审核未通过"},
            ))

    elif directive.action == "resume" and session.supervision_state == "paused":
        await handle_resume(user_id, session)
        system_events = _normalize_system_events(_build_fallback_system_events(directive, session))

    if session.is_bankrupt and directive.action != "complete":
        await send_control(user_id, "downgrade")
        system_events.append("[SYSTEM_EVENT: DEGRADE_MODE_ACTIVE]")

    if not system_events:
        system_events = _normalize_system_events(_build_fallback_system_events(directive, session))

    # Phase 2: call white brain again with system results
    result_context = "\n".join(system_events) if system_events else f"[SYSTEM_RESULT: action={directive.action}, approved={directive.approved}]"
    enriched_text = f"{text}\n{result_context}"
    logger.info(
        "phase2 request, user_id=%s action=%s result_context=%s",
        user_id,
        directive.action,
        _truncate_log_text(result_context),
    )

    phase2_text = await stream_agent_reply(
        user_id=user_id,
        user_text=enriched_text,
        images=images,
        current_task=session.current_plan,
        include_audio=not session.is_bankrupt,
    )
    logger.info("phase2 reply, user_id=%s text=%s", user_id, _truncate_log_text(phase2_text))
    session.append_chat("assistant", phase2_text)


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
        await send_tool_call_status(user_id, "visual.capture", "error", "unknown or expired requestId")
        return

    prompt = str(msg.get("prompt", "")).strip() or (session.pending_capture_prompt or "")
    capture_mode = session.pending_capture_mode
    session.clear_pending_capture()
    if error or not images:
        await send_tool_call_status(user_id, "visual.capture", "error", error or "no images captured")
        await stream_agent_reply(
            user_id=user_id,
            user_text="[SYSTEM_EVENT: VISUAL_CONTEXT_CAPTURE_FAILED]\n我这边还没看到画面，你先确认桌面共享和摄像头权限。",
            images=[],
            current_task=session.current_plan,
            include_audio=not session.is_bankrupt,
        )
        return

    await send_tool_call_status(user_id, "visual.capture", "success", "visual context captured")
    if capture_mode == "direct-chat":
        logger.info("direct visual chat resumed, user_id=%s prompt=%s images=%s", user_id, _truncate_log_text(prompt), len(images))
        phase_text = await stream_agent_reply(
            user_id=user_id,
            user_text=prompt,
            images=images,
            current_task=session.current_plan,
            include_audio=not session.is_bankrupt,
        )
        session.append_chat("assistant", phase_text)
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


async def handle_screenshot(user_id: str, session: SessionState, msg: dict[str, Any]) -> None:
    """Call E vision judgement and C penalty API with threshold arbitration."""
    if session.is_bankrupt:
        return

    images = msg.get("images", [])
    is_distracted = await evaluate_vision(
        images,
        current_task=session.current_plan,
        session_id=user_id,
    )

    if not is_distracted:
        session.distraction_streak = 0
        return

    session.distraction_streak += 1
    if session.distraction_streak < DISTRACTION_THRESHOLD:
        await send_supervision_alert(
            user_id,
            message="检测到注意力波动，请回到当前任务。",
            severity="soft",
            streak_count=session.distraction_streak,
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
        await send_agent_text_chunk(user_id, "请立即停止分心行为，回到学习任务。")
        await send_agent_text_end(user_id)

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


async def handle_start(user_id: str, session: SessionState, duration_seconds: int) -> None:
    """Start supervision and publish state/timer changes."""
    await send_tool_call_status(user_id, "supervision.start", "calling", "starting supervision")
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
        await send_tool_call_status(user_id, "supervision.start", "success", "supervision started")
        return result
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.start", "error", str(exc))
        return None


async def handle_pause(user_id: str, session: SessionState, pause_seconds: int) -> None:
    """Pause supervision and emit updated pause metadata."""
    await send_tool_call_status(user_id, "supervision.pause", "calling", "pausing supervision")
    try:
        session.pause(duration_seconds=pause_seconds)
        await send_supervision_state(user_id, session, reason="approved pause")
        await send_tool_call_status(user_id, "supervision.pause", "success", "supervision paused")
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.pause", "error", str(exc))


async def handle_resume(user_id: str, session: SessionState) -> None:
    """Resume supervision after pause and sync state."""
    await send_tool_call_status(user_id, "supervision.resume", "calling", "resuming supervision")
    try:
        session.resume()
        await send_supervision_state(user_id, session, reason="approved resume")
        await send_tool_call_status(user_id, "supervision.resume", "success", "supervision resumed")
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.resume", "error", str(exc))


async def handle_complete(user_id: str, session: SessionState) -> None:
    """Complete supervision when timer reaches zero."""
    await send_tool_call_status(user_id, "supervision.complete", "calling", "completing session")
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
        await send_tool_call_status(user_id, "supervision.complete", "success", "session completed")
        await _persist_session_summary(user_id, summary_snapshot)
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.complete", "error", str(exc))


async def stream_agent_reply(
    user_id: str,
    user_text: str,
    images: list[dict[str, Any]] | None,
    current_task: str | None,
    include_audio: bool,
) -> str:
    """Stream one white-brain reply; optionally suppress audio in degraded mode.

    Returns the collected reply text.
    """
    parts: list[str] = []
    sent_text = False
    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=user_id,
        images=images,
        current_task=current_task,
    ):
        chunk_text = _sanitize_agent_text(str(chunk.get("text", "")))
        expression = str(chunk.get("expression", "neutral"))
        audio = str(chunk.get("audio", ""))
        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            await send_agent_text_chunk(user_id, chunk_text)
        if include_audio and audio and chunk_text:
            await send_audio(
                user_id,
                audio=audio,
                expression=expression,
                text=chunk_text or "...",
            )

    if sent_text:
        await send_agent_text_end(user_id)
        return "".join(parts)

    fallback = f"收到：{user_text}"
    await send_agent_text_chunk(user_id, fallback)
    await send_agent_text_end(user_id)
    return fallback


async def _stream_and_detect_sys(
    user_id: str,
    user_text: str,
    images: list[dict[str, Any]] | None,
    current_task: str | None,
    include_audio: bool,
) -> tuple[str, bool]:
    """Stream white-brain reply while detecting the <<SYS>> trigger marker.

    Returns (collected_clean_text, sys_detected).
    """
    parts: list[str] = []
    pending_text = ""
    sys_detected = False
    sent_text = False

    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=user_id,
        images=images,
        current_task=current_task,
    ):
        chunk_text = str(chunk.get("text", ""))
        expression = str(chunk.get("expression", "neutral"))
        audio = str(chunk.get("audio", ""))
        emit_text = ""

        if chunk_text:
            emit_text, pending_text, sys_detected = _split_sys_marker_buffer(pending_text + chunk_text)
            if emit_text:
                parts.append(emit_text)
                sent_text = True
                await send_agent_text_chunk(user_id, emit_text)

        if sys_detected:
            logger.info("SYS trigger detected for user_id=%s", user_id)
            pending_text = ""
            continue

        if include_audio and audio and emit_text and not pending_text and emit_text == chunk_text:
            await send_audio(
                user_id,
                audio=audio,
                expression=expression,
                text=emit_text,
            )

    if pending_text and not sys_detected:
        parts.append(pending_text)
        sent_text = True
        await send_agent_text_chunk(user_id, pending_text)

    if sent_text:
        await send_agent_text_end(user_id)
    elif not sys_detected:
        fallback = f"收到：{user_text}"
        parts.append(fallback)
        await send_agent_text_chunk(user_id, fallback)
        await send_agent_text_end(user_id)

    return "".join(parts), sys_detected


async def send_model_info(user_id: str) -> None:
    """Send Live2D model configuration payload."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "model-info",
            "model_info": MODEL_INFO,
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


async def send_control(user_id: str, command: str, payload: dict[str, Any] | None = None) -> None:
    """Emit control command message to frontend."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "control",
            "command": command,
            "payload": payload or {},
        },
    )
