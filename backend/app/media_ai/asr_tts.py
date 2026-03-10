from __future__ import annotations

import asyncio
import io
import math
import os
import struct
import wave
from typing import Protocol


DEFAULT_SAMPLE_RATE = 16000


class ASRService(Protocol):
	async def audio_samples_to_text(self, audio_samples: list[float]) -> str: ...


class TTSService(Protocol):
	async def synthesize(self, text: str, expression: str = "neutral") -> bytes: ...


def pcm16_wav_bytes(audio_samples: list[float], sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
	"""Convert float samples to a mono PCM16 WAV payload."""
	buffer = io.BytesIO()
	with wave.open(buffer, "wb") as wav_file:
		wav_file.setnchannels(1)
		wav_file.setsampwidth(2)
		wav_file.setframerate(sample_rate)
		frames = bytearray()
		for sample in audio_samples:
			clipped = max(-1.0, min(1.0, float(sample)))
			frames.extend(struct.pack("<h", int(clipped * 32767)))
		wav_file.writeframes(bytes(frames))
	return buffer.getvalue()


def synthetic_wav_bytes(
	text: str,
	expression: str = "neutral",
	sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> bytes:
	"""Create a lightweight placeholder WAV for local mock playback."""
	duration_seconds = min(3.0, max(0.45, len(text) * 0.08))
	frame_count = int(sample_rate * duration_seconds)
	base_frequency = {
		"angry": 280.0,
		"encouraging": 520.0,
		"proud": 610.0,
		"sad": 240.0,
		"neutral": 420.0,
	}.get(expression, 420.0)

	samples: list[float] = []
	for index in range(frame_count):
		envelope = 0.18 * math.exp(-index / max(frame_count * 0.85, 1))
		phase = 2.0 * math.pi * base_frequency * (index / sample_rate)
		samples.append(math.sin(phase) * envelope)
	return pcm16_wav_bytes(samples, sample_rate=sample_rate)


class MockASRService:
	"""Deterministic local ASR placeholder for integration tests and demos."""

	async def audio_samples_to_text(self, audio_samples: list[float]) -> str:
		await asyncio.sleep(0)
		if not audio_samples:
			return ""
		duration_seconds = len(audio_samples) / DEFAULT_SAMPLE_RATE
		if duration_seconds < 0.4:
			return "嗯。"
		if duration_seconds < 1.5:
			return "我准备继续学习。"
		return "我会继续专注当前任务。"


class MockTTSService:
	"""Return a synthetic WAV payload so frontend playback can be exercised locally."""

	async def synthesize(self, text: str, expression: str = "neutral") -> bytes:
		await asyncio.sleep(0)
		return synthetic_wav_bytes(text=text, expression=expression)


class EdgeTTSService:
	"""Optional real TTS provider backed by edge-tts when enabled."""

	def __init__(self, voice: str | None = None) -> None:
		self.voice = voice or os.getenv("MEDIA_AI_TTS_VOICE", "zh-CN-XiaoxiaoNeural")

	async def synthesize(self, text: str, expression: str = "neutral") -> bytes:
		try:
			import edge_tts
		except ImportError as exc:
			raise RuntimeError("edge-tts is not installed") from exc

		communicate = edge_tts.Communicate(text=text, voice=self.voice)
		audio_chunks: list[bytes] = []
		async for chunk in communicate.stream():
			if chunk.get("type") == "audio":
				audio_chunks.append(chunk["data"])
		if not audio_chunks:
			return synthetic_wav_bytes(text=text, expression=expression)
		return b"".join(audio_chunks)


def get_asr_service() -> ASRService:
	return MockASRService()


def get_tts_service() -> TTSService:
	provider = os.getenv("MEDIA_AI_TTS_PROVIDER", "mock").lower()
	if provider == "edge":
		return EdgeTTSService()
	return MockTTSService()

