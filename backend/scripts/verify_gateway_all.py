from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import WebSocketDisconnect

from app.auth.security import create_access_token
from app.business.models import SessionLocal, User, Wallet, init_db
from app.gateway.session import SessionState
from app.gateway.ws_router import (
    DISTRACTION_THRESHOLD,
    _stream_and_detect_sys,
    audio_buffers,
    dispatch_message,
    handle_mic_audio_data,
    handle_mic_audio_end,
    handle_screenshot,
    manager,
    run_watchdog,
    watchdog_tasks,
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
    for task in watchdog_tasks.values():
        task.cancel()
    watchdog_tasks.clear()
    audio_buffers.clear()


def sent_types(ws: FakeWebSocket) -> list[str]:
    return [str(item.get("type")) for item in ws.sent]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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
            wallet.balance = balance
        db.commit()
    finally:
        db.close()


async def check_endpoint_handshake_messages() -> None:
    reset_runtime_state()
    ensure_user_balance(1101, 3000)
    ws = FakeWebSocket(
        token=make_token(1101),
        incoming=[{"type": "frontend-playback-complete"}],
    )
    await websocket_endpoint(ws)
    first_three = sent_types(ws)[:3]
    assert_true(
        first_three == ["model-info", "supervision-state-change", "timer-sync"],
        "Endpoint handshake must send model-info, supervision-state-change, timer-sync.",
    )


async def check_tx_dispatch_coverage() -> None:
    reset_runtime_state()
    ensure_user_balance(1102, 3000)
    user_id = "1102"
    ws = FakeWebSocket(token=make_token(1102))
    session = await manager.connect(user_id, ws)

    await dispatch_message(user_id, session, {"type": "mic-audio-data", "audio": [0.1, 0.2]})
    await dispatch_message(user_id, session, {"type": "mic-audio-end", "images": []})
    await dispatch_message(user_id, session, {"type": "text-input", "text": "帮我安排25分钟背单词", "images": []})
    await dispatch_message(user_id, session, {"type": "interrupt-signal", "text": "x"})
    await dispatch_message(
        user_id,
        session,
        {"type": "periodic-screenshot", "images": [{"source": "screen", "data": "1", "mime_type": "image/jpeg"}]},
    )
    await dispatch_message(user_id, session, {"type": "frontend-playback-complete"})

    types = sent_types(ws)
    assert_true("agent-text-chunk" in types, "text-input should produce agent-text-chunk.")
    assert_true("agent-text-end" in types, "text-input should produce agent-text-end.")
    assert_true("plan-update" in types, "plan intent should emit plan-update.")


async def check_audio_pipeline_messages() -> None:
    reset_runtime_state()
    ensure_user_balance(1103, 3000)
    user_id = "1103"
    ws = FakeWebSocket(token=make_token(1103))
    session = await manager.connect(user_id, ws)

    await handle_mic_audio_data(user_id, {"type": "mic-audio-data", "audio": [0.1, -0.2, 0.3]})
    await handle_mic_audio_end(user_id, session, {"type": "mic-audio-end", "images": []})
    types = sent_types(ws)
    assert_true("audio" in types, "mic-audio-end should stream audio packet.")
    assert_true("agent-text-chunk" in types, "mic-audio-end should stream text chunk.")
    assert_true("agent-text-end" in types, "mic-audio-end should end text stream.")


async def check_handshake_bankrupt_downgrade() -> None:
    reset_runtime_state()
    ensure_user_balance(1104, 0)
    ws = FakeWebSocket(token=make_token(1104), incoming=[])
    await websocket_endpoint(ws)
    assert_true(
        any(m.get("type") == "control" and m.get("command") == "downgrade" for m in ws.sent),
        "Bankrupt user should receive downgrade command at handshake.",
    )


async def check_watchdog_timer_completion() -> None:
    reset_runtime_state()
    ensure_user_balance(1105, 3000)
    user_id = "1105"
    ws = FakeWebSocket(token=make_token(1105))
    session = await manager.connect(user_id, ws)
    session.start(duration_seconds=2)

    task = asyncio.create_task(run_watchdog(user_id))
    await asyncio.sleep(2.4)
    if not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert_true(
        session.supervision_state == "completed",
        "Watchdog should complete session when timer reaches zero.",
    )
    assert_true(
        any(m.get("type") == "timer-sync" for m in ws.sent),
        "Watchdog should emit timer-sync events.",
    )


async def check_screenshot_arbitration_and_penalty() -> None:
    reset_runtime_state()
    ensure_user_balance(1106, 5)
    user_id = "1106"
    ws = FakeWebSocket(token=make_token(1106))
    session = await manager.connect(user_id, ws)
    image_msg = {
        "type": "periodic-screenshot",
        "images": [{"source": "screen", "data": "x", "mime_type": "image/jpeg"}],
    }

    for _ in range(DISTRACTION_THRESHOLD):
        await handle_screenshot(user_id, session, image_msg)

    assert_true(session.distraction_streak == 0, "Streak should reset after penalty arbitration.")
    assert_true(session.is_bankrupt, "User should become bankrupt after penalty to zero.")
    assert_true(
        any(m.get("type") == "balance-update" for m in ws.sent),
        "Penalty path should emit balance-update.",
    )
    assert_true(
        any(m.get("type") == "control" and m.get("command") == "downgrade" for m in ws.sent),
        "Bankrupt penalty path should emit downgrade control.",
    )


async def check_state_machine_contract() -> None:
    session = SessionState()
    session.start(10)
    assert_true(session.supervision_state == "active", "start should move setup -> active")
    session.pause(5)
    assert_true(session.supervision_state == "paused", "pause should move active -> paused")
    session.resume()
    assert_true(session.supervision_state == "active", "resume should move paused -> active")
    session.complete()
    assert_true(session.supervision_state == "completed", "complete should move to completed")

    failed = False
    try:
        session.resume()
    except ValueError:
        failed = True
    assert_true(failed, "Invalid transition from completed must be rejected.")


async def check_reconnection_ttl_behavior() -> None:
    from app.gateway.ws_router import ConnectionManager

    local_manager = ConnectionManager(reconnect_ttl_seconds=300)
    ws1 = FakeWebSocket(make_token(1107))
    session1 = await local_manager.connect("1107", ws1)
    session1.distraction_streak = 2
    local_manager.disconnect("1107")

    ws2 = FakeWebSocket(make_token(1107))
    session2 = await local_manager.connect("1107", ws2)
    assert_true(session1 is session2, "Reconnect in TTL should restore same session object.")
    assert_true(session2.distraction_streak == 2, "Reconnect in TTL should keep session data.")

    local_manager.disconnect("1107")
    local_manager.disconnected_at["1107"] = datetime.now(UTC) - timedelta(seconds=301)
    local_manager.cleanup_expired_states()
    assert_true(
        "1107" not in local_manager.user_states,
        "Expired disconnected session should be purged after TTL.",
    )


async def check_protocol_rx_shapes() -> None:
    reset_runtime_state()
    ensure_user_balance(1108, 3000)
    ws = FakeWebSocket(
        token=make_token(1108),
        incoming=[{"type": "text-input", "text": "计划今天背 25 分钟单词", "images": []}],
    )
    await websocket_endpoint(ws)
    types = sent_types(ws)
    assert_true("model-info" in types, "Must emit model-info.")
    assert_true("supervision-state-change" in types, "Must emit supervision-state-change.")
    assert_true("timer-sync" in types, "Must emit timer-sync.")
    assert_true("tool-call-status" in types, "Must emit tool-call-status when updating plan.")
    assert_true("plan-update" in types, "Must emit plan-update when updating plan.")


async def check_visual_capture_tool_flow() -> None:
    reset_runtime_state()
    ensure_user_balance(1109, 3000)
    user_id = "1109"
    ws = FakeWebSocket(token=make_token(1109))
    session = await manager.connect(user_id, ws)

    await dispatch_message(user_id, session, {"type": "text-input", "text": "你帮我看看桌面和摄像头现在是什么情况", "images": []})
    assert_true(
        any(m.get("type") == "control" and m.get("command") == "request-visual-context" for m in ws.sent),
        "Visual inspection request should emit request-visual-context control message.",
    )
    assert_true(
        any(m.get("type") == "agent-text-chunk" and "让我看看" in str(m.get("text", "")) for m in ws.sent),
        "Visual inspection request should first emit the delaying reply.",
    )

    await dispatch_message(
        user_id,
        session,
        {
            "type": "capture-context-result",
            "requestId": "r1",
            "prompt": "你帮我看看桌面和摄像头现在是什么情况",
            "images": [
                {"source": "screen", "data": "abcd" * 100, "mime_type": "image/jpeg"},
                {"source": "camera", "data": "efgh" * 100, "mime_type": "image/jpeg"},
            ],
        },
    )
    types = sent_types(ws)
    assert_true("tool-call-status" in types, "Capture result should emit tool-call-status.")
    assert_true(types.count("agent-text-end") >= 2, "Capture result should lead to a second agent reply.")


async def check_split_sys_marker_detection() -> None:
    reset_runtime_state()
    ensure_user_balance(1110, 3000)
    user_id = "1110"
    ws = FakeWebSocket(token=make_token(1110))
    await manager.connect(user_id, ws)

    async def fake_process_text_chat(**_: object):
        yield {"text": "行，我帮你申请一下。<<S", "expression": "neutral", "audio": "audio-1"}
        yield {"text": "YS>>", "expression": "neutral", "audio": "audio-2"}

    with patch("app.gateway.ws_router.process_text_chat", fake_process_text_chat):
        phase1_text, sys_detected = await _stream_and_detect_sys(
            user_id=user_id,
            user_text="我去上个厕所",
            images=[],
            current_task="测试任务",
            include_audio=True,
        )

    assert_true(sys_detected, "Split SYS marker should still trigger system agent path.")
    assert_true(phase1_text == "行，我帮你申请一下。", "Marker text must be stripped from collected phase-1 text.")
    assert_true(
        not any("<<SYS>>" in str(message.get("text", "")) for message in ws.sent if message.get("type") == "agent-text-chunk"),
        "SYS marker must never leak into streamed chat chunks.",
    )


async def main() -> None:
    checks = [
        ("endpoint_handshake_messages", check_endpoint_handshake_messages),
        ("tx_dispatch_coverage", check_tx_dispatch_coverage),
        ("audio_pipeline_messages", check_audio_pipeline_messages),
        ("handshake_bankrupt_downgrade", check_handshake_bankrupt_downgrade),
        ("watchdog_timer_completion", check_watchdog_timer_completion),
        ("screenshot_arbitration_and_penalty", check_screenshot_arbitration_and_penalty),
        ("state_machine_contract", check_state_machine_contract),
        ("reconnection_ttl_behavior", check_reconnection_ttl_behavior),
        ("protocol_rx_shapes", check_protocol_rx_shapes),
        ("visual_capture_tool_flow", check_visual_capture_tool_flow),
        ("split_sys_marker_detection", check_split_sys_marker_detection),
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
