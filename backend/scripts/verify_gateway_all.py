from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import WebSocketDisconnect

from app.business import api as c_apis
from app.gateway.connection_manager import ConnectionManager
from app.gateway.session import SessionState
from app.gateway.ws_router import (
    DISTRACTION_THRESHOLD,
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

    def __init__(self, user_id: str, incoming: list[dict] | None = None) -> None:
        self.query_params = {"user_id": user_id}
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
    """Reset module-level runtime state between checks."""
    manager.active_connections.clear()
    manager.user_states.clear()
    manager.disconnected_at.clear()
    watchdog_tasks.clear()
    audio_buffers.clear()
    c_apis._balances.clear()


def sent_types(ws: FakeWebSocket) -> list[str]:
    return [str(item.get("type")) for item in ws.sent]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def check_endpoint_handshake_messages() -> None:
    reset_runtime_state()
    ws = FakeWebSocket(
        user_id="u-handshake",
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
    user_id = "u-dispatch"
    ws = FakeWebSocket(user_id=user_id)
    session = await manager.connect(user_id, ws)

    await dispatch_message(user_id, session, {"type": "mic-audio-data", "audio": [0.1, 0.2]})
    await dispatch_message(user_id, session, {"type": "mic-audio-end", "images": []})
    await dispatch_message(user_id, session, {"type": "text-input", "text": "你好", "images": []})
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


async def check_audio_pipeline_messages() -> None:
    reset_runtime_state()
    user_id = "u-audio"
    ws = FakeWebSocket(user_id=user_id)
    session = await manager.connect(user_id, ws)
    session.is_bankrupt = False

    await handle_mic_audio_data(user_id, {"type": "mic-audio-data", "audio": [0.1, -0.2, 0.3]})
    await handle_mic_audio_end(user_id, session, {"type": "mic-audio-end", "images": []})
    types = sent_types(ws)
    assert_true("audio" in types, "mic-audio-end should stream audio packet.")
    assert_true("agent-text-chunk" in types, "mic-audio-end should stream text chunk.")
    assert_true("agent-text-end" in types, "mic-audio-end should end text stream.")


async def check_handshake_bankrupt_downgrade() -> None:
    reset_runtime_state()
    c_apis._balances["u-bankrupt"] = 0
    ws = FakeWebSocket(user_id="u-bankrupt", incoming=[])
    await websocket_endpoint(ws)
    assert_true(
        any(m.get("type") == "control" and m.get("command") == "downgrade" for m in ws.sent),
        "Bankrupt user should receive downgrade command at handshake.",
    )


async def check_watchdog_timer_completion() -> None:
    reset_runtime_state()
    user_id = "u-watchdog"
    ws = FakeWebSocket(user_id=user_id)
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
    user_id = "u-penalty"
    c_apis._balances[user_id] = 5
    ws = FakeWebSocket(user_id=user_id)
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
    local_manager = ConnectionManager(reconnect_ttl_seconds=300)
    ws1 = FakeWebSocket("u-reconnect")
    session1 = await local_manager.connect("u-reconnect", ws1)
    session1.distraction_streak = 2
    local_manager.disconnect("u-reconnect")

    ws2 = FakeWebSocket("u-reconnect")
    session2 = await local_manager.connect("u-reconnect", ws2)
    assert_true(session1 is session2, "Reconnect in TTL should restore same session object.")
    assert_true(session2.distraction_streak == 2, "Reconnect in TTL should keep session data.")

    local_manager.disconnect("u-reconnect")
    local_manager.disconnected_at["u-reconnect"] = datetime.now(UTC) - timedelta(seconds=301)
    local_manager.cleanup_expired_states()
    assert_true(
        "u-reconnect" not in local_manager.user_states,
        "Expired disconnected session should be purged after TTL.",
    )


async def check_protocol_rx_shapes() -> None:
    reset_runtime_state()
    user_id = "u-rx"
    ws = FakeWebSocket(
        user_id=user_id,
        incoming=[{"type": "text-input", "text": "计划", "images": []}],
    )
    await websocket_endpoint(ws)
    types = sent_types(ws)
    assert_true("model-info" in types, "Must emit model-info.")
    assert_true("supervision-state-change" in types, "Must emit supervision-state-change.")
    assert_true("timer-sync" in types, "Must emit timer-sync.")
    assert_true("tool-call-status" in types, "Must emit tool-call-status when updating plan.")
    assert_true("plan-update" in types, "Must emit plan-update when updating plan.")


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
    ]

    passed = 0
    for name, fn in checks:
        await fn()
        passed += 1
        print(f"[PASS] {name}")

    print(f"\nAll checks passed: {passed}/{len(checks)}")


if __name__ == "__main__":
    asyncio.run(main())
