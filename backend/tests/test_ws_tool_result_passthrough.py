import asyncio

from app.gateway.session import SessionState
from app.gateway import ws_router


def test_handle_text_tool_result_skips_user_history(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_handle_user_turn(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(ws_router, "_handle_user_turn", fake_handle_user_turn)

    asyncio.run(
        ws_router.handle_text(
            "42",
            SessionState(),
            {
                "text": "[SYSTEM_RESULT: MOOD_RECORDED, EMOTION: anxious]",
                "tool_result": True,
            },
        )
    )

    assert captured["is_tool_result"] is True
    assert captured["append_user_message"] is False
    assert captured["emit_user_transcript"] is False


def test_handle_text_normal_message_still_appends_user_history(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_handle_user_turn(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(ws_router, "_handle_user_turn", fake_handle_user_turn)

    asyncio.run(
        ws_router.handle_text(
            "42",
            SessionState(),
            {
                "text": "我今天有点焦虑",
                "tool_result": False,
            },
        )
    )

    assert captured["is_tool_result"] is False
    assert captured["append_user_message"] is True
    assert captured["emit_user_transcript"] is False