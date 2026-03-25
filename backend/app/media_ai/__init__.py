from __future__ import annotations

import base64
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from .asr_tts import (
    QWEN_TTS_SAMPLE_RATE,
    create_streaming_tts_session,
    get_asr_service,
    get_tts_service,
    pcm16_bytes_to_wav_bytes,
)
from .client_factory import get_agent_client
from .parser import SentenceBuffer, extract_expression_and_clean, prepare_tts_text, strip_unpronounceable_for_tts


logger = logging.getLogger(__name__)

INVALID_ASR_UTTERANCES = {".", "。", "..", "...", "。。", "。。。"}
SYS_OR_CAPTURE_MARKER_PATTERN = re.compile(r"<<(?:sys|capture)>>", re.IGNORECASE)


def _analyze_markers(text: str) -> tuple[bool, bool, str]:
    has_sys = bool(re.search(r"<<sys>>", text, flags=re.IGNORECASE))
    is_capture = bool(re.search(r"<<capture>>", text, flags=re.IGNORECASE))
    cleaned = SYS_OR_CAPTURE_MARKER_PATTERN.sub("", text)
    return has_sys or is_capture, is_capture, cleaned


async def _build_audio_chunk(
    text: str, expression: str, character_id: str = "milly"
) -> str:
    tts_service = get_tts_service()
    audio_bytes = await tts_service.synthesize(
        text=text, expression=expression, character_id=character_id
    )
    return base64.b64encode(audio_bytes).decode("ascii")


async def _build_audio_chunk_with_service(
    text: str,
    expression: str,
    tts_service: Any,
    character_id: str = "milly",
) -> str:
    # ``text`` is expected to be the pre-expression-stripped sentence (clean_sentence).
    # prepare_tts_text strips both [expression] tags and {kaomoji} entirely.
    tts_text = prepare_tts_text(text)
    if not tts_text:
        return ""
    audio_bytes = await tts_service.synthesize(
        text=tts_text, expression=expression, character_id=character_id
    )
    return base64.b64encode(audio_bytes).decode("ascii")


async def process_text_chat(
    user_text: str,
    session_id: str,
    images: list[dict[str, Any]] | None = None,
    current_task: str | None = None,
    focus_status: str | None = None,
    language_mode: str = "zh",
    character_id: str = "milly",
    skip_audio: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Stream chat response chunks as text, expression, and base64 audio.

    When *skip_audio* is ``True``, ``audio_coro`` is always ``None`` — the
    caller is expected to handle TTS externally (e.g. via a streaming session).
    """
    agent_client = get_agent_client()
    tts_service = None if skip_audio else get_tts_service()
    buffer = SentenceBuffer()

    try:
        async for token in agent_client.stream_chat(
            user_text=user_text,
            session_id=session_id,
            images=images,
            current_task=current_task,
            focus_status=focus_status,
            language_mode=language_mode,
            character_id=character_id,
        ):
            for sentence in buffer.push(token):
                has_sys, is_capture, clean_sentence = _analyze_markers(sentence)
                expression, clean_text = extract_expression_and_clean(clean_sentence)
                if not clean_text and not has_sys:
                    continue
                # tts_text: expression tags + kaomoji stripped entirely (for TTS and streaming TTS).
                tts_text = prepare_tts_text(clean_sentence)
                yield {
                    "text": clean_text,
                    "tts_text": tts_text,
                    "raw_text": sentence,
                    "expression": expression,
                    "sys_triggered": has_sys,
                    "capture_triggered": is_capture,
                    "audio_coro": (
                        _build_audio_chunk_with_service(
                            clean_sentence,
                            expression,
                            tts_service,
                            character_id,
                        )
                        if clean_text and tts_service is not None
                        else None
                    ),
                }

        remainder = buffer.flush()
        if remainder:
            has_sys, is_capture, clean_remainder = _analyze_markers(remainder)
            expression, clean_text = extract_expression_and_clean(clean_remainder)
            if clean_text or has_sys:
                tts_text = prepare_tts_text(clean_remainder)
                yield {
                    "text": clean_text,
                    "tts_text": tts_text,
                    "raw_text": remainder,
                    "expression": expression,
                    "sys_triggered": has_sys,
                    "capture_triggered": is_capture,
                    "audio_coro": (
                        _build_audio_chunk_with_service(
                            clean_remainder,
                            expression,
                            tts_service,
                            character_id,
                        )
                        if clean_text and tts_service is not None
                        else None
                    ),
                }
    except Exception:
        logger.exception("process_text_chat failed, falling back to local response")
        fallback_text = "当前对话服务暂时不可用，我先陪你继续当前任务。"
        yield {
            "text": fallback_text,
            "expression": "neutral",
            "audio_coro": _build_audio_chunk_with_service(
                fallback_text,
                "neutral",
                tts_service,
                character_id,
            ),
        }


async def transcribe_audio(audio_samples: list[float]) -> str:
    """Convert raw float PCM samples into one user utterance string."""
    asr_service = get_asr_service()
    user_text = await asr_service.audio_samples_to_text(audio_samples)
    normalized = user_text.strip()
    if normalized in INVALID_ASR_UTTERANCES:
        logger.info(
            "ignoring punctuation-only ASR transcript as invalid VAD activation"
        )
        return ""
    return normalized


async def process_voice_chat(
    audio_samples: list[float],
    images: list[dict[str, Any]] | None = None,
    session_id: str = "anonymous",
    current_task: str | None = None,
    focus_status: str | None = None,
    language_mode: str = "zh",
    character_id: str = "milly",
) -> AsyncIterator[dict[str, str]]:
    """Transcribe audio first, then reuse the same text chat pipeline."""
    user_text = await transcribe_audio(audio_samples)
    if not user_text:
        return

    async for chunk in process_text_chat(
        user_text=user_text,
        session_id=session_id,
        images=images,
        current_task=current_task,
        focus_status=focus_status,
        language_mode=language_mode,
        character_id=character_id,
    ):
        yield chunk


async def evaluate_vision(
    images: list[dict[str, Any]],
    current_task: str | None = None,
    session_id: str = "anonymous",
) -> tuple[bool, str]:
    """Evaluate distraction verdict through the configured vision provider."""
    agent_client = get_agent_client()
    try:
        return await agent_client.evaluate_vision(
            images=images,
            current_task=current_task,
            session_id=session_id,
        )
    except Exception:
        logger.exception("evaluate_vision failed, defaulting to focused")
        return False, ""


async def evaluate_start_readiness(
    images: list[dict[str, Any]],
    current_task: str | None = None,
    session_id: str = "anonymous",
) -> dict[str, Any]:
    """Evaluate whether camera/screen setup is sufficient to start supervision."""
    agent_client = get_agent_client()
    try:
        return await agent_client.evaluate_start_readiness(
            images=images,
            current_task=current_task,
            session_id=session_id,
        )
    except Exception:
        logger.exception("evaluate_start_readiness failed, defaulting to reject")
        return {
            "approved": False,
            "camera_ok": False,
            "screen_ok": False,
            "reason": "环境检查失败，请重新共享摄像头和屏幕后再试",
        }


__all__ = [
    "evaluate_start_readiness",
    "evaluate_vision",
    "process_text_chat",
    "process_voice_chat",
    "transcribe_audio",
]
