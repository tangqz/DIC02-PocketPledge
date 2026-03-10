from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import struct
import tempfile
import wave
from typing import Protocol


DEFAULT_SAMPLE_RATE = 16000
logger = logging.getLogger(__name__)
_WHISPER_MODELS: dict[tuple[str, str, str], object] = {}


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


class FasterWhisperASRService:
	"""Offline ASR backed by faster-whisper running locally."""

	def __init__(self) -> None:
		self.model_name = os.getenv("MEDIA_AI_ASR_MODEL", "small")
		self.device = os.getenv("MEDIA_AI_ASR_DEVICE", "cpu")
		self.compute_type = os.getenv("MEDIA_AI_ASR_COMPUTE_TYPE", "int8")
		self.language = os.getenv("MEDIA_AI_ASR_LANGUAGE", "zh")
		self.beam_size = max(1, int(os.getenv("MEDIA_AI_ASR_BEAM_SIZE", "3")))

	def _get_model(self):
		cache_key = (self.model_name, self.device, self.compute_type)
		model = _WHISPER_MODELS.get(cache_key)
		if model is not None:
			return model

		from faster_whisper import WhisperModel

		logger.info(
			"Loading faster-whisper model name=%s device=%s compute_type=%s",
			self.model_name,
			self.device,
			self.compute_type,
		)
		model = WhisperModel(
			self.model_name,
			device=self.device,
			compute_type=self.compute_type,
		)
		_WHISPER_MODELS[cache_key] = model
		return model

	def _transcribe_sync(self, wav_bytes: bytes) -> str:
		with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
			temp_file.write(wav_bytes)
			temp_path = temp_file.name

		try:
			model = self._get_model()
			segments, _info = model.transcribe(
				temp_path,
				language=self.language,
				beam_size=self.beam_size,
				vad_filter=False,
				condition_on_previous_text=False,
			)
			text = "".join(segment.text for segment in segments).strip()
			return text
		finally:
			try:
				os.unlink(temp_path)
			except OSError:
				logger.debug("Failed to remove temp ASR file: %s", temp_path)

	async def audio_samples_to_text(self, audio_samples: list[float]) -> str:
		if not audio_samples:
			return ""

		wav_bytes = pcm16_wav_bytes(audio_samples)
		try:
			text = await asyncio.to_thread(self._transcribe_sync, wav_bytes)
			if text:
				return text
			logger.warning("faster-whisper returned empty transcript")
		except Exception:
			logger.exception("faster-whisper transcription failed")
		return ""


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
	provider = os.getenv("MEDIA_AI_ASR_PROVIDER", "faster-whisper").lower()
	if provider in {"faster-whisper", "whisper", "local"}:
		return FasterWhisperASRService()
	return MockASRService()


def get_tts_service() -> TTSService:
	provider = os.getenv("MEDIA_AI_TTS_PROVIDER", "mock").lower()
	if provider == "edge":
		return EdgeTTSService()
	return MockTTSService()

