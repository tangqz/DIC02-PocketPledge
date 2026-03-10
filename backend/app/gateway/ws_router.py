from __future__ import annotations

import asyncio
import uuid
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth.security import decode_access_token
from app.business.models import SessionLocal
from app.business.crud import (
    execute_penalty as db_execute_penalty,
    get_user_status as db_get_user_status,
    start_focus_session as db_start_focus_session,
)
from app.gateway.session import SessionState
from app.media_ai import evaluate_vision, process_text_chat, process_voice_chat
from app.system_agent import SystemAgentService

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manage active websocket connections and in-memory session states."""

    def __init__(self, reconnect_ttl_seconds: int = 300) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.user_states: dict[str, SessionState] = {}
        self.disconnected_at: dict[str, datetime] = {}
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
            return
        await websocket.send_json(payload)

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
PENALTY_AMOUNT = 5
BOT_NAME = "Study Buddy"
DEFAULT_BALANCE = 100
SYS_MARKER = "<<SYS>>"

watchdog_tasks: dict[str, asyncio.Task] = {}
audio_buffers: dict[str, list[float]] = {}
system_agent = SystemAgentService()


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

    task = watchdog_tasks.get(user_id)
    if task is None or task.done():
        watchdog_tasks[user_id] = asyncio.create_task(run_watchdog(user_id))

    await send_model_info(user_id)
    await send_supervision_state(user_id, session)
    await send_timer_sync(user_id, session)
    if session.is_bankrupt:
        await send_control(user_id, "downgrade")

    try:
        while True:
            message = await ws.receive_json()
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
    sent_text = False
    async for chunk in process_voice_chat(
        audio_samples,
        images,
        session_id=user_id,
        current_task=session.current_plan,
    ):
        text = str(chunk.get("text", ""))
        expression = str(chunk.get("expression", "neutral"))
        audio = str(chunk.get("audio", ""))

        if text:
            sent_text = True
            await send_agent_text_chunk(user_id, text)
        if audio:
            await send_audio(user_id, audio=audio, expression=expression, text=text or "...")

    if sent_text:
        await send_agent_text_end(user_id)


async def handle_text(user_id: str, session: SessionState, msg: dict[str, Any]) -> None:
    """Handle text-input: white-brain-first with <<SYS>> trigger for system agent.

    Phase 1: stream white brain reply while detecting <<SYS>> marker.
    If no <<SYS>>: done (simple chat).
    If <<SYS>> detected:
      - Call system agent for structured directive
      - Execute directive (start/pause/resume/complete/plan/visual-capture)
      - Phase 2: call white brain again with [SYSTEM_RESULT: ...] context
    """
    text = str(msg.get("text", ""))
    images = msg.get("images", [])
    is_tool_result = bool(msg.get("tool_result"))
    logger.info("text-input received, user_id=%s text=%s", user_id, text)

    session.append_chat("user", text)

    # Phase 1: stream white brain, detect <<SYS>> trigger
    phase1_text, sys_detected = await _stream_and_detect_sys(
        user_id=user_id,
        user_text=text,
        images=images,
        current_task=session.current_plan,
        include_audio=not session.is_bankrupt,
    )

    if not sys_detected:
        session.append_chat("assistant", phase1_text)
        return

    # <<SYS>> detected — invoke system agent for structured directive
    directive = await system_agent.build_directive(user_id, text, session)
    system_events = list(directive.system_events)

    # Handle visual capture request
    if directive.requires_capture and not images and not is_tool_result:
        await send_tool_call_status(user_id, "visual.capture", "calling", "capturing visual context")
        await send_control(
            user_id,
            "request-visual-context",
            {
                "requestId": uuid.uuid4().hex,
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
        tasks = directive.plan.get("tasks") or []
        if tasks:
            session.current_plan = str(tasks[0].get("title", session.current_plan or "完成当前学习任务"))
        session.suggested_focus_seconds = int(directive.plan.get("suggestedDuration") or DEFAULT_TOTAL_SECONDS)
        await send_plan_update(user_id, directive.plan)
        await send_tool_call_status(user_id, "plan.update", "success", "plan updated")

    elif directive.action == "start" and session.supervision_state == "setup":
        duration_seconds = directive.duration_seconds or session.suggested_focus_seconds or DEFAULT_TOTAL_SECONDS
        await handle_start(user_id, session, duration_seconds=duration_seconds)

    elif directive.action == "pause" and session.supervision_state == "active":
        session.pause_requests_count += 1
        if directive.approved:
            await handle_pause(user_id, session, pause_seconds=directive.pause_seconds or 300)
        else:
            await send_tool_call_status(user_id, "supervision.pause", "error", "pause rejected")

    elif directive.action == "resume" and session.supervision_state == "paused":
        await handle_resume(user_id, session)

    if session.is_bankrupt and directive.action != "complete":
        await send_control(user_id, "downgrade")
        system_events.append("[SYSTEM_EVENT: DEGRADE_MODE_ACTIVE]")

    # Phase 2: call white brain again with system results
    result_event = f"[SYSTEM_RESULT: action={directive.action}, approved={directive.approved}]"
    if system_events:
        result_context = "\n".join([result_event, *system_events])
    else:
        result_context = result_event
    enriched_text = f"{text}\n{result_context}"

    phase2_text = await stream_agent_reply(
        user_id=user_id,
        user_text=enriched_text,
        images=images,
        current_task=session.current_plan,
        include_audio=not session.is_bankrupt,
    )
    session.append_chat("assistant", phase2_text)


async def handle_capture_context_result(
    user_id: str,
    session: SessionState,
    msg: dict[str, Any],
) -> None:
    """Resume one chat turn after frontend capture tool returns images."""
    images = msg.get("images", [])
    error = str(msg.get("error", "")).strip()
    prompt = str(msg.get("prompt", "")).strip()
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
    await handle_text(
        user_id,
        session,
        {
            "type": "text-input",
            "text": prompt,
            "images": images,
            "tool_result": True,
        },
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
        await send_tool_call_status(user_id, "supervision.start", "success", "supervision started")
    except ValueError as exc:
        await send_tool_call_status(user_id, "supervision.start", "error", str(exc))


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
        session.complete()
        await send_supervision_state(user_id, session, reason="time up")
        await send_timer_sync(user_id, session)
        await send_tool_call_status(user_id, "supervision.complete", "success", "session completed")
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
        chunk_text = str(chunk.get("text", ""))
        expression = str(chunk.get("expression", "neutral"))
        audio = str(chunk.get("audio", ""))
        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            await send_agent_text_chunk(user_id, chunk_text)
        if include_audio and audio:
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

        if SYS_MARKER in chunk_text:
            sys_detected = True
            clean = chunk_text.replace(SYS_MARKER, "").strip()
            if clean:
                parts.append(clean)
                sent_text = True
                await send_agent_text_chunk(user_id, clean)
            continue

        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            await send_agent_text_chunk(user_id, chunk_text)
        if include_audio and audio:
            await send_audio(
                user_id,
                audio=audio,
                expression=expression,
                text=chunk_text or "...",
            )

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
    await manager.send_personal_message(
        user_id,
        {
            "type": "agent-text-chunk",
            "text": text,
        },
    )


async def send_agent_text_end(user_id: str) -> None:
    """Mark the end of one agent text streaming turn."""
    await manager.send_personal_message(user_id, {"type": "agent-text-end"})


async def send_audio(user_id: str, audio: str, expression: str, text: str) -> None:
    """Send audio packet in frontend contract shape."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "audio",
            "audio": audio,
            "actions": {"expressions": [expression]},
            "display_text": {"text": text, "name": BOT_NAME},
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
