from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

os.environ["AGENT_BACKEND"] = "mock"
os.environ["MEDIA_AI_ASR_PROVIDER"] = "mock"
os.environ["MEDIA_AI_TTS_PROVIDER"] = "mock"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import WebSocketDisconnect

from app.auth.security import create_access_token
from app.business.models import SessionLocal, User, Wallet, init_db
from app.gateway.ws_router import (
    _stream_and_detect_sys,
    audio_buffers,
    dispatch_message,
    handle_mic_audio_data,
    handle_mic_audio_end,
    handle_screenshot,
    manager,
    websocket_endpoint,
)


class FakeWebSocket:
    """Minimal websocket test double for gateway verification."""

    def __init__(self, token: str, incoming: list[dict] | None = None) -> None:
        self.query_params = {"token": token}
        self.headers: dict[str, str] = {}
        self._incoming = list(incoming or [])
        self.sent: list[dict] = []
        self.accepted = False
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self) -> dict:
        if self._incoming:
            return self._incoming.pop(0)
        raise WebSocketDisconnect()

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        _ = (code, reason)
        self.closed = True


def reset_runtime_state() -> None:
    manager.active_connections.clear()
    manager.user_states.clear()
    manager.disconnected_at.clear()
    manager.pending_messages.clear()
    audio_buffers.clear()


def sent_types(ws: FakeWebSocket) -> list[str]:
    return [str(item.get("type")) for item in ws.sent]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def as_ws(fake_ws: FakeWebSocket) -> Any:
    return cast(Any, fake_ws)


def make_token(user_id: int) -> str:
    return create_access_token(user_id=user_id, username=f"user_{user_id}")


def ensure_user_balance(user_id: int, balance: int) -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user:
            user = User(id=user_id, username=f"verify_{user_id}", role="user")
            db.add(user)
            db.flush()

        wallet = db.get(Wallet, user_id)
        if not wallet:
            wallet = Wallet(user_id=user_id, balance=balance)
            db.add(wallet)
        else:
            setattr(wallet, "balance", balance)

        db.commit()
    finally:
        db.close()


async def check_endpoint_handshake_messages() -> None:
    reset_runtime_state()
    ensure_user_balance(2101, 3000)
    ws = FakeWebSocket(token=make_token(2101), incoming=[])
    await websocket_endpoint(as_ws(ws))
    types = sent_types(ws)
    assert_true(bool(types), "Handshake should send at least one message.")
    assert_true(types[0] == "model-info", "First handshake message must be model-info.")


async def check_text_input_stream() -> None:
    reset_runtime_state()
    ensure_user_balance(2102, 3000)
    user_id = "2102"
    ws = FakeWebSocket(token=make_token(2102))
    session = await manager.connect(user_id, as_ws(ws))

    with patch("app.gateway.ws_router.create_streaming_tts_session", return_value=None):
        await dispatch_message(
            user_id,
            session,
            {"type": "text-input", "text": "今天有点累，想聊聊", "images": []},
        )

    types = sent_types(ws)
    assert_true("agent-text-chunk" in types, "text-input should produce agent-text-chunk.")
    assert_true("agent-text-end" in types, "text-input should produce agent-text-end.")


async def check_character_switch_and_ping() -> None:
    reset_runtime_state()
    ensure_user_balance(2103, 3000)
    user_id = "2103"
    ws = FakeWebSocket(token=make_token(2103))
    session = await manager.connect(user_id, as_ws(ws))

    await dispatch_message(user_id, session, {"type": "set-character", "characterId": "ren"})
    await dispatch_message(user_id, session, {"type": "ping"})

    assert_true(
        any(m.get("type") == "model-info" for m in ws.sent),
        "set-character should emit model-info.",
    )
    assert_true(
        any(
            m.get("type") == "control" and m.get("command") == "chat-cleared"
            for m in ws.sent
        ),
        "set-character should emit chat-cleared control.",
    )
    assert_true(
        any(
            m.get("type") == "control" and m.get("command") == "pong"
            for m in ws.sent
        ),
        "ping should receive pong control.",
    )


async def check_capture_roundtrip_flow() -> None:
    reset_runtime_state()
    ensure_user_balance(2104, 3000)
    user_id = "2104"
    ws = FakeWebSocket(token=make_token(2104))
    session = await manager.connect(user_id, as_ws(ws))

    with patch("app.gateway.ws_router.create_streaming_tts_session", return_value=None):
        await dispatch_message(
            user_id,
            session,
            {
                "type": "text-input",
                "text": "你看看我现在状态",
                "images": [],
            },
        )

    request_control = next(
        (
            m
            for m in ws.sent
            if m.get("type") == "control"
            and m.get("command") == "request-visual-context"
        ),
        None,
    )
    assert_true(
        request_control is not None,
        "Visual request should emit request-visual-context control.",
    )

    request_id = str((request_control or {}).get("payload", {}).get("requestId", ""))
    assert_true(bool(request_id), "request-visual-context payload must include requestId.")
    assert_true(
        any(
            m.get("type") == "tool-call-status"
            and m.get("tool") == "visual.capture"
            and m.get("status") == "calling"
            for m in ws.sent
        ),
        "Capture request should emit visual.capture calling status.",
    )

    async def fake_followup_chat(**_: object):
        yield {
            "text": "我看到了你，状态还不错。",
            "raw_text": "我看到了你，状态还不错。",
            "expression": "happy",
            "audio_coro": None,
        }

    with (
        patch("app.gateway.ws_router.process_text_chat", fake_followup_chat),
        patch("app.gateway.ws_router.create_streaming_tts_session", return_value=None),
    ):
        await dispatch_message(
            user_id,
            session,
            {
                "type": "capture-context-result",
                "requestId": request_id,
                "prompt": "你看看我现在状态",
                "images": [
                    {
                        "source": "camera",
                        "data": "abcd" * 100,
                        "mime_type": "image/jpeg",
                    }
                ],
            },
        )

    assert_true(
        any(
            m.get("type") == "tool-call-status"
            and m.get("tool") == "visual.capture"
            and m.get("status") == "success"
            for m in ws.sent
        ),
        "capture-context-result should emit visual.capture success.",
    )
    assert_true(
        sent_types(ws).count("agent-text-end") >= 2,
        "Capture roundtrip should lead to a follow-up assistant response.",
    )


async def check_voice_pipeline_messages() -> None:
    reset_runtime_state()
    ensure_user_balance(2105, 3000)
    user_id = "2105"
    ws = FakeWebSocket(token=make_token(2105))
    session = await manager.connect(user_id, as_ws(ws))

    await handle_mic_audio_data(
        user_id,
        {
            "type": "mic-audio-data",
            "audio": [0.1, -0.2, 0.05],
        },
    )
    with (
        patch("app.gateway.ws_router.transcribe_audio", AsyncMock(return_value="你好")),
        patch("app.gateway.ws_router.create_streaming_tts_session", return_value=None),
    ):
        await handle_mic_audio_end(
            user_id,
            session,
            {"type": "mic-audio-end", "images": []},
        )

    types = sent_types(ws)
    assert_true("user-transcript" in types, "mic-audio-end should emit user-transcript.")
    assert_true("agent-text-end" in types, "mic-audio-end should produce agent-text-end.")


async def check_screenshot_emotion_update() -> None:
    reset_runtime_state()
    ensure_user_balance(2106, 3000)
    user_id = "2106"
    ws = FakeWebSocket(token=make_token(2106))
    session = await manager.connect(user_id, as_ws(ws))

    with (
        patch(
            "app.gateway.ws_router.evaluate_vision",
            AsyncMock(
                return_value={
                    "emotion": "anxious",
                    "intensity": 4,
                    "cues": "brows tense",
                    "suggestion": "slow breathing",
                }
            ),
        ),
        patch("app.gateway.ws_router.create_streaming_tts_session", return_value=None),
    ):
        await handle_screenshot(
            user_id,
            session,
            {
                "type": "periodic-screenshot",
                "images": [
                    {
                        "source": "camera",
                        "data": "x",
                        "mime_type": "image/jpeg",
                    }
                ],
            },
        )

    assert_true(
        any(m.get("type") == "emotion-update" for m in ws.sent),
        "periodic-screenshot should emit emotion-update.",
    )


async def check_split_sys_marker_detection() -> None:
    reset_runtime_state()
    ensure_user_balance(2107, 3000)
    user_id = "2107"
    ws = FakeWebSocket(token=make_token(2107))
    await manager.connect(user_id, as_ws(ws))

    async def fake_process_text_chat(**_: object):
        yield {
            "text": "我来处理一下。",
            "raw_text": "我来处理一下。",
            "expression": "neutral",
            "audio_coro": None,
        }
        yield {
            "text": "",
            "raw_text": "<<SYS>>",
            "expression": "neutral",
            "audio_coro": None,
        }

    with (
        patch("app.gateway.ws_router.process_text_chat", fake_process_text_chat),
        patch("app.gateway.ws_router.create_streaming_tts_session", return_value=None),
    ):
        phase1_text, sys_detected, capture_detected, _ = await _stream_and_detect_sys(
            user_id=user_id,
            user_text="测试",
            images=[],
            current_task=None,
            language_mode="zh",
            character_id="milly",
            include_audio=True,
            detect_sys=True,
            on_sys_detected=None,
        )

    assert_true(sys_detected, "SYS marker should trigger system-agent path.")
    assert_true(not capture_detected, "SYS marker case should not trigger capture path.")
    assert_true(phase1_text == "我来处理一下。", "SYS marker text must not leak into visible reply.")
    assert_true(
        not any(
            "<<SYS>>" in str(message.get("text", ""))
            for message in ws.sent
            if message.get("type") == "agent-text-chunk"
        ),
        "SYS marker must never leak to frontend chunks.",
    )


async def check_reconnection_ttl_behavior() -> None:
    from app.gateway.ws_router import ConnectionManager

    local_manager = ConnectionManager(reconnect_ttl_seconds=300)
    ws1 = FakeWebSocket(make_token(2108))
    session1 = await local_manager.connect("2108", as_ws(ws1))
    session1.distraction_streak = 2  # type: ignore[attr-defined]
    local_manager.disconnect("2108")

    ws2 = FakeWebSocket(make_token(2108))
    session2 = await local_manager.connect("2108", as_ws(ws2))
    assert_true(
        session1 is session2,
        "Reconnect in TTL should restore same session object.",
    )

    local_manager.disconnect("2108")
    local_manager.disconnected_at["2108"] = datetime.now(UTC) - timedelta(seconds=301)
    local_manager.cleanup_expired_states()
    assert_true(
        "2108" not in local_manager.user_states,
        "Expired disconnected session should be purged after TTL.",
    )


async def main() -> None:
    checks = [
        ("endpoint_handshake_messages", check_endpoint_handshake_messages),
        ("text_input_stream", check_text_input_stream),
        ("character_switch_and_ping", check_character_switch_and_ping),
        ("capture_roundtrip_flow", check_capture_roundtrip_flow),
        ("voice_pipeline_messages", check_voice_pipeline_messages),
        ("screenshot_emotion_update", check_screenshot_emotion_update),
        ("split_sys_marker_detection", check_split_sys_marker_detection),
        ("reconnection_ttl_behavior", check_reconnection_ttl_behavior),
    ]

    init_db()
    passed = 0
    for name, fn in checks:
        await fn()
        passed += 1
        print(f"[PASS] {name}")

    print(f"\nAll checks passed: {passed}/{len(checks)}")


if __name__ == "__main__":
    asyncio.run(main())
