from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator
from typing import Any

from .asr_tts import get_asr_service, get_tts_service
from .dify_proxy import get_dify_client
from .parser import SentenceBuffer, extract_expression_and_clean


logger = logging.getLogger(__name__)


async def _build_audio_chunk(text: str, expression: str) -> str:
	tts_service = get_tts_service()
	audio_bytes = await tts_service.synthesize(text=text, expression=expression)
	return base64.b64encode(audio_bytes).decode("ascii")


async def _build_audio_chunk_with_service(text: str, expression: str, tts_service: Any) -> str:
	audio_bytes = await tts_service.synthesize(text=text, expression=expression)
	return base64.b64encode(audio_bytes).decode("ascii")


async def process_text_chat(
	user_text: str,
	session_id: str,
	images: list[dict[str, Any]] | None = None,
	current_task: str | None = None,
) -> AsyncIterator[dict[str, str]]:
	"""Stream chat response chunks as text, expression, and base64 audio."""
	dify_client = get_dify_client()
	tts_service = get_tts_service()
	buffer = SentenceBuffer()

	try:
		async for token in dify_client.stream_chat(
			user_text=user_text,
			session_id=session_id,
			images=images,
			current_task=current_task,
		):
			for sentence in buffer.push(token):
				expression, clean_text = extract_expression_and_clean(sentence)
				if not clean_text:
					continue
				yield {
					"text": clean_text,
					"expression": expression,
					"audio": await _build_audio_chunk_with_service(
						clean_text,
						expression,
						tts_service,
					),
				}

		remainder = buffer.flush()
		if remainder:
			expression, clean_text = extract_expression_and_clean(remainder)
			if clean_text:
				yield {
					"text": clean_text,
					"expression": expression,
					"audio": await _build_audio_chunk_with_service(
						clean_text,
						expression,
						tts_service,
					),
				}
	except Exception:
		logger.exception("process_text_chat failed, falling back to local response")
		fallback_text = "当前对话服务暂时不可用，我先陪你继续当前任务。"
		yield {
			"text": fallback_text,
			"expression": "neutral",
			"audio": await _build_audio_chunk_with_service(
				fallback_text,
				"neutral",
				tts_service,
			),
		}


async def transcribe_audio(audio_samples: list[float]) -> str:
	"""Convert raw float PCM samples into one user utterance string."""
	asr_service = get_asr_service()
	user_text = await asr_service.audio_samples_to_text(audio_samples)
	return user_text.strip()


async def process_voice_chat(
	audio_samples: list[float],
	images: list[dict[str, Any]] | None = None,
	session_id: str = "anonymous",
	current_task: str | None = None,
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
	):
		yield chunk


async def evaluate_vision(
	images: list[dict[str, Any]],
	current_task: str | None = None,
	session_id: str = "anonymous",
) -> bool:
    """Evaluate distraction verdict through the configured vision provider."""
    dify_client = get_dify_client()
    try:
        return await dify_client.evaluate_vision(
            images=images,
            current_task=current_task,
            session_id=session_id,
        )
    except Exception:
        logger.exception("evaluate_vision failed, defaulting to focused")
        return False


__all__ = [
	"evaluate_vision",
	"process_text_chat",
	"process_voice_chat",
	"transcribe_audio",
]
