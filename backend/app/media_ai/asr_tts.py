from __future__ import annotations

import asyncio
import io
import logging
import math
import os
from pathlib import Path
import struct
import tempfile
import wave
from typing import Any, Protocol, cast

import numpy as np


DEFAULT_SAMPLE_RATE = 16000
logger = logging.getLogger(__name__)
_WHISPER_MODELS: dict[tuple[str, str, str], object] = {}
_SHERPA_RECOGNIZERS: dict[tuple[str, str, str, int, bool, str], object] = {}


def _default_sherpa_model_dir() -> Path:
	repo_root = Path(__file__).resolve().parents[3]
	candidates = [
		repo_root.parent / "Open-LLM-VTuber" / "models" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
		repo_root / "Open-LLM-VTuber" / "models" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
	]
	for candidate in candidates:
		if candidate.exists():
			return candidate
	return candidates[0]


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
			model = cast(Any, self._get_model())
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


class SherpaOnnxASRService:
	"""Offline ASR backed by sherpa-onnx SenseVoice, aligned with Open-LLM-VTuber."""

	def __init__(self) -> None:
		default_model_dir = _default_sherpa_model_dir()
		self.model_type = os.getenv("MEDIA_AI_SHERPA_MODEL_TYPE", "sense_voice")
		self.model_path = Path(
			os.getenv(
				"MEDIA_AI_SHERPA_MODEL_PATH",
				str(default_model_dir / "model.int8.onnx"),
			)
		)
		self.tokens_path = Path(
			os.getenv(
				"MEDIA_AI_SHERPA_TOKENS_PATH",
				str(default_model_dir / "tokens.txt"),
			)
		)
		self.num_threads = max(1, int(os.getenv("MEDIA_AI_SHERPA_NUM_THREADS", "2")))
		self.provider = os.getenv("MEDIA_AI_SHERPA_PROVIDER", "cpu").lower()
		self.use_itn = os.getenv("MEDIA_AI_SHERPA_USE_ITN", "1").lower() not in {"0", "false", "no"}

	def _get_recognizer(self):
		cache_key = (
			self.model_type,
			str(self.model_path),
			str(self.tokens_path),
			self.num_threads,
			self.use_itn,
			self.provider,
		)
		recognizer = _SHERPA_RECOGNIZERS.get(cache_key)
		if recognizer is not None:
			return recognizer

		if self.model_type != "sense_voice":
			raise RuntimeError(f"Unsupported Sherpa model_type={self.model_type}; only sense_voice is wired in backend")
		if not self.model_path.exists():
			raise RuntimeError(
				"Sherpa model not found. Set MEDIA_AI_SHERPA_MODEL_PATH or place the SenseVoice model under "
				f"{self.model_path}"
			)
		if not self.tokens_path.exists():
			raise RuntimeError(
				"Sherpa tokens.txt not found. Set MEDIA_AI_SHERPA_TOKENS_PATH or place tokens under "
				f"{self.tokens_path}"
			)

		import onnxruntime
		import sherpa_onnx

		provider = self.provider
		if provider == "cuda" and "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
			logger.warning("Sherpa CUDA provider unavailable, falling back to CPU")
			provider = "cpu"

		logger.info(
			"Loading sherpa-onnx ASR model_type=%s model=%s provider=%s",
			self.model_type,
			self.model_path,
			provider,
		)
		recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
			model=str(self.model_path),
			tokens=str(self.tokens_path),
			num_threads=self.num_threads,
			use_itn=self.use_itn,
			provider=provider,
		)
		_SHERPA_RECOGNIZERS[cache_key] = recognizer
		return recognizer

	def _transcribe_sync(self, audio_samples: list[float]) -> str:
		recognizer = cast(Any, self._get_recognizer())
		audio = np.asarray(audio_samples, dtype=np.float32)
		stream = recognizer.create_stream()
		stream.accept_waveform(DEFAULT_SAMPLE_RATE, audio)
		recognizer.decode_streams([stream])
		return stream.result.text.strip()

	async def audio_samples_to_text(self, audio_samples: list[float]) -> str:
		if not audio_samples:
			return ""
		try:
			return await asyncio.to_thread(self._transcribe_sync, audio_samples)
		except Exception:
			logger.exception("sherpa-onnx transcription failed")
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
				data = chunk.get("data")
				if isinstance(data, bytes):
					audio_chunks.append(data)
		if not audio_chunks:
			return synthetic_wav_bytes(text=text, expression=expression)
		return b"".join(audio_chunks)


def get_asr_service() -> ASRService:
	provider = os.getenv("MEDIA_AI_ASR_PROVIDER", "sherpa-onnx").lower()
	if provider in {"sherpa-onnx", "sherpa_onnx", "sherpa_onnx_asr"}:
		return SherpaOnnxASRService()
	if provider in {"faster-whisper", "whisper", "local"}:
		return FasterWhisperASRService()
	return MockASRService()


def get_tts_service() -> TTSService:
	provider = os.getenv("MEDIA_AI_TTS_PROVIDER", "mock").lower()
	if provider == "edge":
		return EdgeTTSService()
	return MockTTSService()

