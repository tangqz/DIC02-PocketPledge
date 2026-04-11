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
    append_user_profile_memory as db_append_user_profile_memory,
    create_chat_message as db_create_chat_message,
    create_mood_entry as db_create_mood_entry,
    create_session_summary as db_create_session_summary,
    get_user_profile_document as db_get_user_profile_document,
    list_recent_chat_messages as db_list_recent_chat_messages,
)
from app.gateway.session import SessionState
from app.media_ai import (
    QWEN_TTS_SAMPLE_RATE,
    create_streaming_tts_session,
    evaluate_vision,
    pcm16_bytes_to_wav_bytes,
    process_text_chat,
    strip_unpronounceable_for_tts,
    transcribe_audio,
)
from app.system_agent import SystemAgentService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Connection & session management
# ---------------------------------------------------------------------------

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
                user_id, len(queued_messages),
            )
            for payload in queued_messages:
                await self.send_personal_message(user_id, payload)
        return session

    def disconnect(self, user_id: str, websocket: WebSocket | None = None) -> bool:
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
        websocket = self.active_connections.get(user_id)
        if websocket is None:
            logger.warning(
                "ws tx queued user_id=%s reason=no-active-connection payload=%s",
                user_id, _summarize_payload(payload),
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
        failed_users: list[str] = []
        for user_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.exception("broadcast send failed user_id=%s", user_id)
                failed_users.append(user_id)
        for user_id in failed_users:
            self.active_connections.pop(user_id, None)
            self.disconnected_at[user_id] = datetime.now(UTC)

    def cleanup_expired_states(self) -> None:
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


# ---------------------------------------------------------------------------
# Character catalog
# ---------------------------------------------------------------------------

CHARACTER_CATALOG: dict[str, dict[str, Any]] = {
    "milly": {
        "name": "milly",
        "displayName": "Milly",
        "description": "Warm emotional companion. Empathetic and encouraging.",
        "languageHints": ["zh", "en"],
        "personaStyle": "warm-companion",
        "modelInfo": {
            "name": "mao_pro",
            "url": "/live2d-models/mao_pro/mao_pro.model3.json",
            "kScale": 1.0,
            "emotionMap": {
                "neutral": 0, "happy": 3, "encouraging": 4,
                "angry": 2, "proud": 7,
            },
            "idleMotionGroup": "Idle",
            "talkMotionGroup": "",
        },
    },
    "ren": {
        "name": "natori",
        "displayName": "Natori",
        "description": "Calm mindfulness guide. Grounding and peaceful.",
        "languageHints": ["zh", "en"],
        "personaStyle": "calm-guide",
        "modelInfo": {
            "name": "natori_pro_zh",
            "url": "/live2d-models/natori_pro_zh/runtime/natori_pro_t06.model3.json",
            "kScale": 1.0,
            "emotionMap": {
                "neutral": 2, "happy": 4, "encouraging": 4,
                "angry": 0, "proud": 4,
            },
            "idleMotionGroup": "Idle",
            "talkMotionGroup": "Tap",
        },
    },
}
DEFAULT_CHARACTER_ID = "milly"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOT_NAME = "WarmBuddy"
SYS_MARKER = "<<SYS>>"
CAPTURE_MARKER = "<<CAPTURE>>"
LOG_PREVIEW_LIMIT = 240
CAPTURE_SOURCES = ["camera"]
MAX_AGENT_STAGES = 6

audio_buffers: dict[str, list[float]] = {}
system_agent = SystemAgentService()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _parse_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        n = int(value)
        return n if n >= 0 else default
    except (TypeError, ValueError):
        return default


def _truncate_log_text(value: Any, limit: int = LOG_PREVIEW_LIMIT) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


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
                {"source": item.get("source"), "mime_type": item.get("mime_type"),
                 "data": f"<{len(str(item.get('data', '')))} base64 chars>"}
                for item in value[:4] if isinstance(item, dict)
            ]
            if len(value) > 4:
                summary[key].append({"remaining": len(value) - 4})
            continue
        if isinstance(value, str):
            summary[key] = _truncate_log_text(value)
            continue
        if isinstance(value, dict):
            summary[key] = {k: _truncate_log_text(v) for k, v in value.items()}
            continue
        if isinstance(value, list):
            summary[key] = f"<list len={len(value)}>"
            continue
        summary[key] = value
    return json.dumps(summary, ensure_ascii=False)


def _split_sys_marker_buffer(buffer: str) -> tuple[str, str, bool]:
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
    cleaned = re.sub(r"<<\s*sys\s*>>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<<\s*capture\s*>>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _is_english_mode(language_mode: str) -> bool:
    return str(language_mode).strip().lower() == "en"


def _build_auto_greeting_event(language_mode: str) -> str:
    if _is_english_mode(language_mode):
        return (
            "[SYSTEM_EVENT: USER_CONNECTED] "
            "The user just opened the app. Greet them with one short warm sentence."
        )
    return "[SYSTEM_EVENT: USER_CONNECTED] 用户刚刚打开了应用，用一句温暖的话打招呼。"


def _build_emotion_event_instruction(language_mode: str, tired: bool) -> str:
    if _is_english_mode(language_mode):
        if tired:
            return "The user seems tired. Offer a brief and gentle rest reminder."
        return "The user seems emotionally down. Offer gentle care in 1-2 short sentences."
    if tired:
        return "用户看起来比较疲惫，请提醒休息。"
    return "用户看起来情绪不太好，请用1-2句话温柔关心。"


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------

async def _persist_chat_message(
    user_id: str, role: str, content: str, session_ref: str | None
) -> None:
    try:
        uid = int(user_id)
    except ValueError:
        return
    db = SessionLocal()
    try:
        db_create_chat_message(db=db, user_id=uid, role=role, content=content, session_ref=session_ref)
    except Exception:
        logger.exception("failed to persist chat message, user_id=%s role=%s", user_id, role)
    finally:
        db.close()


async def _persist_mood_entry(
    user_id: str,
    mood_data: dict[str, Any],
    source: str,
    session_ref: str | None,
) -> dict[str, Any] | None:
    try:
        uid = int(user_id)
    except ValueError:
        return None

    emotion = str(mood_data.get("emotion", "neutral")).strip().lower() or "neutral"
    intensity = max(1, min(_parse_non_negative_int(mood_data.get("intensity"), 1), 5))
    cues = str(mood_data.get("cues", "")).strip()
    suggestion = str(mood_data.get("suggestion", "")).strip()
    context = cues
    if suggestion:
        context = f"{cues} | suggestion: {suggestion}" if cues else f"suggestion: {suggestion}"

    meal_info = str(mood_data.get("meal_info", "")).strip()
    meal_emotion = str(mood_data.get("meal_emotion", "")).strip()
    normalized_source = str(source or mood_data.get("source") or "chat").strip().lower() or "chat"

    db = SessionLocal()
    try:
        return db_create_mood_entry(
            db=db,
            user_id=uid,
            emotion=emotion,
            intensity=intensity,
            context=context,
            meal_info=meal_info,
            meal_emotion=meal_emotion,
            source=normalized_source,
            session_ref=session_ref,
        )
    except Exception:
        logger.exception("failed to persist mood entry, user_id=%s source=%s", user_id, normalized_source)
        return None
    finally:
        db.close()


async def _append_chat(session: SessionState, user_id: str, role: str, content: str) -> None:
    session.append_chat(role, content)
    await _persist_chat_message(user_id=user_id, role=role, content=content, session_ref=session.session_ref)
    await _process_profile_rollover(session=session, user_id=user_id)


def _format_chat_messages_for_profile_rollover(messages: list[dict[str, str]], character_id: str) -> str:
    speaker_name = "Ren" if character_id == "ren" else "米莉"
    lines: list[str] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if role == "user":
            prefix = "用户"
        elif role == "assistant":
            prefix = speaker_name
        else:
            prefix = "系统"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


async def _process_profile_rollover(session: SessionState, user_id: str) -> None:
    batch = session.pop_profile_rollover_batch()
    if not batch:
        return
    try:
        uid = int(user_id)
    except ValueError:
        return
    rotated_chat = _format_chat_messages_for_profile_rollover(batch, session.character_id)
    if not rotated_chat.strip():
        return
    db = SessionLocal()
    try:
        existing_profile = str(db_get_user_profile_document(db=db, user_id=uid).get("content", ""))
    except Exception:
        logger.exception("failed to load profile for rollover, user_id=%s", user_id)
        return
    finally:
        db.close()
    memory_lines = await system_agent.extract_profile_memories(
        session_id=user_id, rotated_chat=rotated_chat, existing_profile=existing_profile,
    )
    if not memory_lines:
        return
    db = SessionLocal()
    try:
        for line in memory_lines:
            db_append_user_profile_memory(db=db, user_id=uid, memory_line=line)
    except Exception:
        logger.exception("failed to append profile rollover memory, user_id=%s", user_id)
    finally:
        db.close()


async def _hydrate_chat_history(user_id: str, session: SessionState) -> None:
    if session.chat_history:
        return
    try:
        uid = int(user_id)
    except ValueError:
        return
    db = SessionLocal()
    try:
        result = db_list_recent_chat_messages(db=db, user_id=uid, limit=session.MAX_HISTORY_TURNS)
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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _authenticate_ws_token(token: str | None) -> int | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WarmBuddy WebSocket hub — auth, hydrate, greet, loop."""
    token = ws.query_params.get("token")
    user_id_int = _authenticate_ws_token(token)
    if user_id_int is None:
        await ws.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required"
        )
        return
    user_id = str(user_id_int)

    session = await manager.connect(user_id, ws)
    requested_locale = str(ws.query_params.get("locale") or "").strip().lower()
    if requested_locale in {"zh", "en"}:
        session.language_mode = requested_locale

    requested_character_id = (
        str(ws.query_params.get("characterId") or "").strip().lower()
    )
    if requested_character_id in CHARACTER_CATALOG:
        session.character_id = requested_character_id

    await _hydrate_chat_history(user_id, session)
    await send_model_info(user_id, session)

    # Auto-greeting for fresh sessions
    if not session.chat_history:
        asyncio.create_task(_send_auto_greeting(user_id, session))

    try:
        while True:
            try:
                message = await ws.receive_json()
            except RuntimeError as exc:
                logger.info("WebSocket receive ended, user_id=%s error=%s", user_id, exc)
                break
            asyncio.create_task(dispatch_message(user_id, session, message))
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected, user_id=%s", user_id)
    finally:
        disconnected_current = manager.disconnect(user_id, ws)
        if disconnected_current:
            audio_buffers.pop(user_id, None)


async def _send_auto_greeting(user_id: str, session: SessionState) -> None:
    """Send a one-line greeting when user first connects."""
    try:
        greeting = await stream_agent_reply(
            user_id=user_id,
            user_text=_build_auto_greeting_event(session.language_mode),
            images=[],
            current_task=None,
            language_mode=session.language_mode,
            character_id=session.character_id,
            include_audio=True,
        )
        if greeting:
            await _append_chat(session, user_id, "assistant", greeting)
    except Exception:
        logger.exception("auto-greeting failed, user_id=%s", user_id)


# ---------------------------------------------------------------------------
# Message dispatch
# ---------------------------------------------------------------------------

async def dispatch_message(
    user_id: str, session: SessionState, msg: dict[str, Any]
) -> None:
    """Route frontend messages by protocol type."""
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
        logger.info("interrupt-signal received, user_id=%s", user_id)
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
            session.clear_chat_context()
            await send_model_info(user_id, session)
            await send_control(
                user_id,
                "chat-cleared",
                {"reason": "character_switched", "characterId": character_id},
            )
        return

    if msg_type == "ping":
        await send_control(user_id, "pong")
        return

    logger.warning("Unknown message type: %s", msg_type)


# ---------------------------------------------------------------------------
# User input handlers
# ---------------------------------------------------------------------------

async def handle_mic_audio_data(user_id: str, msg: dict[str, Any]) -> None:
    samples = msg.get("audio", [])
    if not isinstance(samples, list):
        return
    bucket = audio_buffers.setdefault(user_id, [])
    bucket.extend(float(item) for item in samples if isinstance(item, (int, float)))


async def handle_mic_audio_end(
    user_id: str, session: SessionState, msg: dict[str, Any]
) -> None:
    audio_samples = audio_buffers.pop(user_id, [])
    images = msg.get("images", [])
    logger.info("mic-audio-end received, user_id=%s samples=%s", user_id, len(audio_samples))
    user_text = await transcribe_audio(audio_samples)
    if not user_text:
        logger.info("ignoring empty ASR transcript as noise, user_id=%s", user_id)
        return
    logger.info("ASR transcript generated, user_id=%s text=%s", user_id, user_text)
    await _handle_user_turn(
        user_id=user_id, session=session, text=user_text, images=images,
        is_tool_result=False, emit_user_transcript=True,
    )


async def handle_text(user_id: str, session: SessionState, msg: dict[str, Any]) -> None:
    text = str(msg.get("text", ""))
    images = msg.get("images", [])
    is_tool_result = bool(msg.get("tool_result"))
    await _handle_user_turn(
        user_id=user_id, session=session, text=text, images=images,
        is_tool_result=is_tool_result, emit_user_transcript=False,
    )


# ---------------------------------------------------------------------------
# Core two-phase agent orchestration
# ---------------------------------------------------------------------------

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
    """White-brain-first with optional <<SYS>> system-agent follow-up.

    Phase 1: stream white brain reply, detect <<SYS>>/<<CAPTURE>>.
    If <<CAPTURE>>: request camera capture, return.
    If no <<SYS>>: done (simple chat).
    If <<SYS>>: call system agent → execute mood/profile action → phase 2.
    """
    logger.info("text-input received, user_id=%s text=%s", user_id, text)

    if stage_depth >= MAX_AGENT_STAGES:
        logger.warning("agent stage limit reached, user_id=%s", user_id)
        await send_tool_call_status(user_id, "orchestration", "error", "stage limit reached")
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

    # Phase 1: stream white brain, detect <<SYS>>/<<CAPTURE>>
    (
        phase1_text,
        sys_detected,
        capture_detected,
        directive_task,
    ) = await _stream_and_detect_sys(
        user_id=user_id,
        user_text=text,
        images=images,
        current_task=None,
        language_mode=session.language_mode,
        character_id=session.character_id,
        include_audio=True,
        detect_sys=not is_tool_result,
        on_sys_detected=(_run_system_agent if not is_tool_result else None),
    )

    # <<CAPTURE>> detected — request visual context from frontend
    if capture_detected:
        await _append_chat(session, user_id, "assistant", phase1_text)
        request_id = uuid.uuid4().hex
        session.set_pending_capture(request_id, text, CAPTURE_SOURCES, mode="chat")
        await send_tool_call_status(user_id, "visual.capture", "calling", "direct visual request")
        await send_control(
            user_id, "request-visual-context",
            {"requestId": request_id, "prompt": text, "sources": CAPTURE_SOURCES},
        )
        return

    # No <<SYS>> — simple chat turn
    if not sys_detected:
        await _append_chat(session, user_id, "assistant", phase1_text)
        return

    logger.info(
        "phase1 handoff accepted, user_id=%s assistant_text=%s",
        user_id, _truncate_log_text(phase1_text),
    )

    # <<SYS>> detected — get system directive
    directive = await (directive_task or asyncio.create_task(_run_system_agent()))
    if directive.error_message:
        await send_tool_call_status(user_id, "system.agent", "error", directive.error_message)
        await _handle_user_turn(
            user_id=user_id, session=session,
            text=f"[SYSTEM_RESULT: SYSTEM_AGENT_ERROR, DETAIL: {_truncate_log_text(directive.error_message)}]",
            images=images, is_tool_result=True, append_user_message=False,
            emit_user_transcript=False, stage_depth=stage_depth + 1,
        )
        return

    await send_tool_call_status(user_id, "system.agent", "success", f"action={directive.action}")
    system_events = [e for e in directive.system_events if isinstance(e, str) and e.strip()]

    # Handle visual capture request from system agent
    if directive.requires_capture:
        if not images and not is_tool_result:
            request_id = uuid.uuid4().hex
            session.set_pending_capture(request_id, text, CAPTURE_SOURCES, mode="system-agent")
            await send_tool_call_status(user_id, "visual.capture", "calling", "capturing visual context")
            await send_control(
                user_id, "request-visual-context",
                {"requestId": request_id, "prompt": text, "sources": CAPTURE_SOURCES},
            )
            return

    # Execute directive actions
    if directive.action == "mood" and directive.mood_data:
        mood = directive.mood_data
        mood_saved = await _persist_mood_entry(
            user_id=user_id,
            mood_data=mood,
            source=str(mood.get("source") or "chat"),
            session_ref=session.session_ref,
        )
        total_reward = int((mood_saved or {}).get("total_reward", 0))
        system_events.append(
            f"[SYSTEM_RESULT: MOOD_RECORDED, EMOTION: {mood.get('emotion', 'neutral')}, "
            f"INTENSITY: {mood.get('intensity', 1)}, POINTS: +{total_reward}]"
        )
        if total_reward > 0:
            system_events.append(f"[SYSTEM_RESULT: REWARD_GRANTED, POINTS: +{total_reward}]")
        session.record_emotion(mood)
        await send_emotion_update(user_id, mood)

    elif directive.action == "profile":
        system_events.append("[SYSTEM_RESULT: PROFILE_NOTED]")

    # Follow-up: pass system results back to white brain
    if not system_events:
        system_events = [f"[SYSTEM_RESULT: action={directive.action}, approved={directive.approved}]"]

    result_context = "\n".join(system_events)
    logger.info(
        "follow-up request, user_id=%s stage=%s action=%s result_context=%s",
        user_id, stage_depth + 1, directive.action, _truncate_log_text(result_context),
    )
    await _handle_user_turn(
        user_id=user_id, session=session, text=result_context,
        images=images, is_tool_result=True, append_user_message=False,
        emit_user_transcript=False, stage_depth=stage_depth + 1,
    )


# ---------------------------------------------------------------------------
# Capture context result handler
# ---------------------------------------------------------------------------

async def handle_capture_context_result(
    user_id: str, session: SessionState, msg: dict[str, Any],
) -> None:
    """Resume chat turn after frontend capture tool returns images."""
    images = msg.get("images", [])
    error = str(msg.get("error", "")).strip()
    request_id = str(msg.get("requestId", "")).strip()
    if not request_id or request_id != session.pending_capture_request_id:
        await send_tool_call_status(user_id, "visual.capture", "error", "unknown or expired requestId")
        return

    prompt = str(msg.get("prompt", "")).strip() or (session.pending_capture_prompt or "")
    session.clear_pending_capture()

    if error or not images:
        await send_tool_call_status(user_id, "visual.capture", "error", error or "no images captured")
        await _handle_user_turn(
            user_id=user_id, session=session,
            text=(f"{prompt}\n[SYSTEM_EVENT: VISUAL_CONTEXT_CAPTURE_FAILED]" if prompt
                  else "[SYSTEM_EVENT: VISUAL_CONTEXT_CAPTURE_FAILED]"),
            images=[], is_tool_result=True, append_user_message=False,
            emit_user_transcript=False, stage_depth=1,
        )
        return

    await send_tool_call_status(user_id, "visual.capture", "success", "visual context captured")
    await _handle_user_turn(
        user_id=user_id, session=session, text=prompt, images=images,
        is_tool_result=True, append_user_message=False, emit_user_transcript=False,
    )


# ---------------------------------------------------------------------------
# Vision: temporal image stitching + emotion recognition
# ---------------------------------------------------------------------------

def _build_temporal_stitched_image(
    session: SessionState, current_images: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    import time
    import io
    import base64
    from collections import defaultdict
    from PIL import Image, ImageDraw, ImageFont

    MAX_BASE64_SIZE = 5 * 1024 * 1024

    client_timestamps = []
    for img in current_images:
        meta = img.get("metadata", {})
        if "timestamp" in meta and isinstance(meta["timestamp"], (int, float)):
            client_timestamps.append(meta["timestamp"])

    relative_now_ms = (
        max(client_timestamps) if client_timestamps else time.time() * 1000
    )

    grouped_images: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for img in current_images:
        meta = img.get("metadata", {})
        ts_ms = meta.get("timestamp")
        if not isinstance(ts_ms, (int, float)):
            ts_ms = relative_now_ms
        grouped_images[int(ts_ms)].append(img)

    sorted_groups = sorted(grouped_images.items(), key=lambda x: x[0], reverse=True)[:6]

    MAX_SRC_HEIGHT = 240
    MIN_ROW_HEIGHT = 200
    row_images = []

    try:
        font = ImageFont.load_default(size=24)
    except Exception:
        font = ImageFont.load_default()

    for ts_ms, imgs in sorted_groups:
        pil_imgs = []
        for img_dict in imgs:
            b64 = str(img_dict.get("data", ""))
            if not b64:
                continue
            if len(b64) > MAX_BASE64_SIZE:
                logger.warning("skipping oversized image in stitcher: %d bytes", len(b64))
                continue
            try:
                img_data = base64.b64decode(b64)
                img = Image.open(io.BytesIO(img_data)).convert("RGB")
                if img.height > MAX_SRC_HEIGHT:
                    scale = MAX_SRC_HEIGHT / img.height
                    img = img.resize(
                        (int(img.width * scale), MAX_SRC_HEIGHT),
                        Image.Resampling.LANCZOS,
                    )
                pil_imgs.append(img)
            except Exception:
                pass

        if not pil_imgs:
            continue

        row_height = max(max(img.height for img in pil_imgs), MIN_ROW_HEIGHT)

        scaled_imgs = []
        total_w = 0
        for pimg in pil_imgs:
            w, h = pimg.size
            if h == row_height:
                scaled_imgs.append(pimg)
                total_w += w
            else:
                new_w = int(w * (row_height / h))
                scaled = pimg.resize((new_w, row_height), Image.Resampling.LANCZOS)
                scaled_imgs.append(scaled)
                total_w += new_w

        group_img = Image.new("RGB", (total_w, row_height))
        x_offset = 0
        for sc in scaled_imgs:
            group_img.paste(sc, (x_offset, 0))
            x_offset += sc.width

        dt = int((relative_now_ms - ts_ms) / 1000)
        label = "T" if dt <= 1 else f"T-{dt}s"
        txt_height = 30

        row_final = Image.new(
            "RGB", (group_img.width, group_img.height + txt_height), color=(30, 30, 30)
        )
        row_final.paste(group_img, (0, txt_height))
        draw = ImageDraw.Draw(row_final)
        draw.text((5, 5), label, fill=(255, 255, 0), font=font)
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
    final_img.save(buf, format="JPEG", quality=80)
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
    """Evaluate user emotion from periodic camera captures."""
    images = msg.get("images", [])
    if images:
        images_for_vision = _build_temporal_stitched_image(session, images)
    else:
        images_for_vision = []

    emotion_result = await evaluate_vision(
        images_for_vision, session_id=user_id,
    )

    emotion = str(emotion_result.get("emotion", "neutral"))
    intensity = int(emotion_result.get("intensity", 1))

    session.record_emotion(emotion_result)
    await send_emotion_update(user_id, emotion_result)
    mood_saved = await _persist_mood_entry(
        user_id=user_id,
        mood_data=emotion_result,
        source="camera",
        session_ref=session.session_ref,
    )
    total_reward = int((mood_saved or {}).get("total_reward", 0))
    if total_reward > 0:
        await send_tool_call_status(
            user_id,
            "reward.mood",
            "success",
            f"+{total_reward} points",
        )

    # React to strong negative emotions
    if emotion in ("sad", "anxious", "stressed", "angry") and intensity >= 3:
        prompt = (
            f"[SYSTEM_EVENT: EMOTION_DETECTED, emotion={emotion}, intensity={intensity}, "
            f"cues={emotion_result.get('cues', '')}]\n"
            f"{_build_emotion_event_instruction(session.language_mode, tired=False)}"
        )
        await _handle_user_turn(
            user_id=user_id, session=session, text=prompt, images=[],
            is_tool_result=True, append_user_message=False,
            emit_user_transcript=False, stage_depth=1,
        )
    elif emotion == "tired" and intensity >= 3:
        prompt = (
            f"[SYSTEM_EVENT: EMOTION_DETECTED, emotion=tired, intensity={intensity}]\n"
            f"{_build_emotion_event_instruction(session.language_mode, tired=True)}"
        )
        await _handle_user_turn(
            user_id=user_id, session=session, text=prompt, images=[],
            is_tool_result=True, append_user_message=False,
            emit_user_transcript=False, stage_depth=1,
        )


# ---------------------------------------------------------------------------
# Streaming agent reply
# ---------------------------------------------------------------------------

async def _run_streaming_audio_reader(
    tts_session: Any, user_id: str, expression: str,
) -> None:
    """Background: read PCM chunks from streaming TTS, wrap in WAV, send to frontend."""
    import base64 as _b64

    while True:
        pcm_chunk = await tts_session.read_audio_chunk()
        if pcm_chunk is None:
            break
        if not pcm_chunk:
            continue
        try:
            wav_bytes = pcm16_bytes_to_wav_bytes(pcm_chunk, sample_rate=QWEN_TTS_SAMPLE_RATE)
            audio_b64 = _b64.b64encode(wav_bytes).decode("ascii")
            await send_audio_stream_chunk(user_id, audio=audio_b64, expression=expression)
        except Exception:
            logger.exception("streaming TTS audio send failed, user_id=%s", user_id)
    await send_audio_stream_end(user_id, expression=expression)


async def stream_agent_reply(
    user_id: str,
    user_text: str,
    images: list[dict[str, Any]] | None,
    current_task: str | None,
    language_mode: str,
    character_id: str,
    include_audio: bool,
) -> str:
    """Stream one white-brain reply. Returns the collected reply text."""
    tts_session = create_streaming_tts_session(character_id=character_id) if include_audio else None
    use_streaming = tts_session is not None
    audio_reader_task: asyncio.Task[Any] | None = None

    if use_streaming:
        try:
            await tts_session.start()
        except Exception:
            logger.warning("streaming TTS session start failed, falling back", exc_info=True)
            tts_session = None
            use_streaming = False

    parts: list[str] = []
    sent_text = False
    last_expression = "neutral"
    audio_tasks: list[tuple[asyncio.Task[Any], str, str]] = []

    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=user_id,
        images=images,
        current_task=current_task,
        focus_status=None,
        language_mode=language_mode,
        character_id=character_id,
        skip_audio=use_streaming,
    ):
        chunk_text = _sanitize_agent_text(str(chunk.get("text", "")))
        expression = str(chunk.get("expression", "neutral"))
        audio_coro = chunk.get("audio_coro")
        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            last_expression = expression
            await send_agent_text_chunk(user_id, chunk_text)
            if expression:
                await send_control(user_id, "set-expression", {"expression": expression})

        if use_streaming and chunk_text:
            tts_feed = str(chunk.get("tts_text", ""))
            if tts_feed:
                if audio_reader_task is None:
                    audio_reader_task = asyncio.create_task(
                        _run_streaming_audio_reader(tts_session, user_id, last_expression)
                    )
                await tts_session.append_text(tts_feed)

        if not use_streaming and include_audio and audio_coro is not None and chunk_text:
            audio_task = asyncio.create_task(audio_coro)
            audio_tasks.append((audio_task, expression, chunk_text))

    if use_streaming and tts_session is not None:
        try:
            await tts_session.finish()
        except Exception:
            logger.exception("streaming TTS finish failed, user_id=%s", user_id)
        if audio_reader_task is not None:
            try:
                await audio_reader_task
            except Exception:
                logger.exception("streaming TTS reader task failed, user_id=%s", user_id)

    for task, expression, chunk_text in audio_tasks:
        try:
            audio_data = await task
            if audio_data:
                await send_audio(user_id, audio=audio_data, expression=expression, text=chunk_text or "...")
        except Exception:
            logger.exception("Failed to generate audio for chunk")

    if sent_text:
        await send_agent_text_end(user_id)
        return "".join(parts)

    logger.warning("empty white-brain reply, user_id=%s text=%s", user_id, _truncate_log_text(user_text))
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
    detect_sys: bool = True,
    on_sys_detected: Callable[[], Coroutine[Any, Any, Any]] | None = None,
) -> tuple[str, bool, bool, asyncio.Task[Any] | None]:
    """Stream white-brain reply while detecting <<SYS>> and <<CAPTURE>> markers.

    Returns (collected_clean_text, sys_detected, capture_detected, directive_task).
    """
    tts_session = create_streaming_tts_session(character_id=character_id) if include_audio else None
    use_streaming = tts_session is not None
    audio_reader_task: asyncio.Task[Any] | None = None

    if use_streaming:
        try:
            await tts_session.start()
        except Exception:
            logger.warning("streaming TTS session start failed, falling back", exc_info=True)
            tts_session = None
            use_streaming = False

    parts: list[str] = []
    sys_detected = False
    capture_detected = False
    sent_text = False
    sys_task: asyncio.Task[Any] | None = None
    last_expression = "neutral"
    audio_tasks: list[tuple[asyncio.Task[Any], str, str]] = []

    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=user_id,
        images=images,
        current_task=current_task,
        focus_status=None,
        language_mode=language_mode,
        character_id=character_id,
        skip_audio=use_streaming,
    ):
        chunk_text = _sanitize_agent_text(str(chunk.get("text", "")))
        raw_text = str(chunk.get("raw_text", ""))
        expression = str(chunk.get("expression", "neutral"))
        audio_coro = chunk.get("audio_coro")
        raw_upper = raw_text.upper()
        chunk_sys_triggered = (
            bool(chunk.get("sys_triggered")) or SYS_MARKER in raw_upper
        )
        chunk_capture_triggered = (
            bool(chunk.get("capture_triggered")) or CAPTURE_MARKER in raw_upper
        )

        if chunk_text:
            parts.append(chunk_text)
            sent_text = True
            last_expression = expression
            await send_agent_text_chunk(user_id, chunk_text)
            if expression:
                await send_control(user_id, "set-expression", {"expression": expression})

        if chunk_capture_triggered and not capture_detected:
            capture_detected = True
            logger.info("CAPTURE trigger detected for user_id=%s", user_id)

        if (
            detect_sys
            and chunk_sys_triggered
            and not sys_detected
            and not chunk_capture_triggered
        ):
            sys_detected = True
            logger.info("SYS trigger detected for user_id=%s", user_id)
            if on_sys_detected is not None:
                sys_task = asyncio.create_task(on_sys_detected())

        if use_streaming and chunk_text:
            tts_feed = str(chunk.get("tts_text", ""))
            if tts_feed:
                if audio_reader_task is None:
                    audio_reader_task = asyncio.create_task(
                        _run_streaming_audio_reader(tts_session, user_id, last_expression)
                    )
                await tts_session.append_text(tts_feed)

        if not use_streaming and include_audio and audio_coro is not None and chunk_text:
            audio_task = asyncio.create_task(audio_coro)
            audio_tasks.append((audio_task, expression, chunk_text))

    if use_streaming and tts_session is not None:
        try:
            await tts_session.finish()
        except Exception:
            logger.exception("streaming TTS finish failed, user_id=%s", user_id)
        if audio_reader_task is not None:
            try:
                await audio_reader_task
            except Exception:
                logger.exception("streaming TTS reader task failed, user_id=%s", user_id)

    for task, expression, chunk_text in audio_tasks:
        try:
            audio_data = await task
            if audio_data:
                await send_audio(user_id, audio=audio_data, expression=expression, text=chunk_text)
        except Exception:
            logger.exception("Failed to generate audio for chunk")

    if sent_text:
        await send_agent_text_end(user_id)
    elif not sys_detected and not capture_detected:
        logger.warning("empty phase1 reply without SYS or CAPTURE, user_id=%s", user_id)
        await send_agent_text_end(user_id)

    return "".join(parts), sys_detected, capture_detected, sys_task


# ---------------------------------------------------------------------------
# Send helpers
# ---------------------------------------------------------------------------

def _resolve_character(session: SessionState) -> tuple[str, dict[str, Any]]:
    character_id = (
        session.character_id
        if session.character_id in CHARACTER_CATALOG
        else DEFAULT_CHARACTER_ID
    )
    return character_id, CHARACTER_CATALOG[character_id]


async def send_model_info(user_id: str, session: SessionState) -> None:
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


async def send_agent_text_chunk(user_id: str, text: str) -> None:
    clean_text = _sanitize_agent_text(text)
    if not clean_text:
        return
    await manager.send_personal_message(
        user_id, {"type": "agent-text-chunk", "text": clean_text},
    )


async def send_user_transcript(user_id: str, text: str) -> None:
    await manager.send_personal_message(
        user_id, {"type": "user-transcript", "text": text},
    )


async def send_agent_text_end(user_id: str) -> None:
    await manager.send_personal_message(user_id, {"type": "agent-text-end"})


async def send_audio(user_id: str, audio: str, expression: str, text: str) -> None:
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


async def send_audio_stream_chunk(user_id: str, audio: str, expression: str) -> None:
    await manager.send_personal_message(
        user_id, {"type": "audio-stream-chunk", "audio": audio, "expression": expression},
    )


async def send_audio_stream_end(user_id: str, expression: str) -> None:
    await manager.send_personal_message(
        user_id, {"type": "audio-stream-end", "expression": expression},
    )


async def send_emotion_update(user_id: str, emotion_data: dict[str, Any]) -> None:
    """Send emotion recognition result to frontend."""
    await manager.send_personal_message(
        user_id,
        {
            "type": "emotion-update",
            "emotion": emotion_data.get("emotion", "neutral"),
            "intensity": emotion_data.get("intensity", 1),
            "cues": emotion_data.get("cues", ""),
            "suggestion": emotion_data.get("suggestion", ""),
        },
    )


async def send_tool_call_status(
    user_id: str, tool: str, status: str, message: str
) -> None:
    await manager.send_personal_message(
        user_id,
        {"type": "tool-call-status", "tool": tool, "status": status, "message": message},
    )


async def send_control(
    user_id: str, command: str, payload: dict[str, Any] | None = None
) -> None:
    await manager.send_personal_message(
        user_id,
        {"type": "control", "command": command, "payload": payload or {}},
    )
