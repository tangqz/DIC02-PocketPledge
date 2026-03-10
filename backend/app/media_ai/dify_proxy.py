from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx


logger = logging.getLogger(__name__)


def _pick_text_payload(payload: Any) -> str:
	if isinstance(payload, str):
		return payload
	if isinstance(payload, dict):
		for key in ("answer", "text", "delta", "content"):
			value = payload.get(key)
			if isinstance(value, str) and value.strip():
				return value
		data = payload.get("data")
		if data is not None:
			return _pick_text_payload(data)
	return ""


def _pick_bool_payload(payload: Any) -> bool | None:
	if isinstance(payload, bool):
		return payload
	if isinstance(payload, dict):
		for key in ("is_distracted", "distracted", "result"):
			value = payload.get(key)
			verdict = _pick_bool_payload(value)
			if verdict is not None:
				return verdict
		data = payload.get("data")
		if data is not None:
			return _pick_bool_payload(data)
	return None


class MockDifyClient:
	"""Local deterministic fallback for chat streaming and vision evaluation."""

	async def stream_chat(
		self,
		user_text: str,
		session_id: str,
		images: list[dict[str, Any]] | None = None,
		current_task: str | None = None,
	) -> AsyncIterator[str]:
		_ = session_id
		lower_text = user_text.lower()
		if "开始" in user_text:
			reply = "[encouraging]好的，我们开始今天的专注任务吧。"
		elif "计划" in user_text:
			reply = "[proud]我已经记住你的计划了，先完成最重要的一步。"
		elif "暂停" in user_text:
			reply = "[neutral]如果确实有必要，请尽快回来继续。"
		elif "完成" in user_text or "done" in lower_text:
			reply = "[proud]做得不错，我们继续保持这个节奏。"
		else:
			reply = "[encouraging]我在，继续专注当前任务。"

		if current_task:
			reply += f"[neutral]当前目标是{current_task}。"
		if images:
			reply += "[neutral]我会结合你刚刚提供的画面继续陪你。"

		for token in reply:
			await asyncio.sleep(0)
			yield token

	async def evaluate_vision(
		self,
		images: list[dict[str, Any]],
		current_task: str | None = None,
		session_id: str | None = None,
	) -> bool:
		_ = (current_task, session_id)
		if not images:
			return False

		for image in images:
			source = str(image.get("source", "")).lower()
			hint = str(image.get("hint", "")).lower()
			if any(keyword in hint for keyword in ("phone", "video", "game", "social")):
				return True
			if source == "screen" and len(str(image.get("data", ""))) < 128:
				return True
		return False


class DifyClient:
	"""Real Dify proxy with SSE chat support and blocking workflow support."""

	def __init__(self) -> None:
		self.base_url = os.getenv("DIFY_API_BASE", "").rstrip("/")
		self.chat_endpoint = os.getenv("DIFY_CHAT_ENDPOINT", "/v1/chat-messages")
		self.vision_endpoint = os.getenv("DIFY_VISION_ENDPOINT", "/v1/workflows/run")
		self.chat_api_key = os.getenv("DIFY_CHAT_API_KEY", "")
		self.vision_api_key = os.getenv("DIFY_VISION_API_KEY", self.chat_api_key)
		self.timeout = float(os.getenv("MEDIA_AI_HTTP_TIMEOUT", "20"))

	async def stream_chat(
		self,
		user_text: str,
		session_id: str,
		images: list[dict[str, Any]] | None = None,
		current_task: str | None = None,
	) -> AsyncIterator[str]:
		if not self.base_url or not self.chat_api_key:
			raise RuntimeError("Missing Dify chat configuration")

		payload = {
			"inputs": {
				"current_task": current_task or "",
				"images": images or [],
			},
			"query": user_text,
			"response_mode": "streaming",
			"conversation_id": session_id,
			"user": session_id,
		}
		headers = {
			"Authorization": f"Bearer {self.chat_api_key}",
			"Content-Type": "application/json",
			"Accept": "text/event-stream",
		}

		async with httpx.AsyncClient(timeout=self.timeout) as client:
			async with client.stream(
				"POST",
				f"{self.base_url}{self.chat_endpoint}",
				json=payload,
				headers=headers,
			) as response:
				response.raise_for_status()
				async for line in response.aiter_lines():
					if not line or not line.startswith("data:"):
						continue
					data = line[5:].strip()
					if data == "[DONE]":
						break
					try:
						event = json.loads(data)
					except json.JSONDecodeError:
						logger.debug("skip non-json SSE payload: %s", data)
						continue
					text = _pick_text_payload(event)
					if text:
						yield text

	async def evaluate_vision(
		self,
		images: list[dict[str, Any]],
		current_task: str | None = None,
		session_id: str | None = None,
	) -> bool:
		if not self.base_url or not self.vision_api_key:
			raise RuntimeError("Missing Dify vision configuration")

		image_payload = images[0] if images else {}
		payload = {
			"inputs": {
				"image_base64": image_payload.get("data", ""),
				"image_source": image_payload.get("source", ""),
				"current_task": current_task or "",
			},
			"response_mode": "blocking",
			"user": session_id or "vision-anonymous",
		}
		headers = {
			"Authorization": f"Bearer {self.vision_api_key}",
			"Content-Type": "application/json",
		}

		async with httpx.AsyncClient(timeout=self.timeout) as client:
			response = await client.post(
				f"{self.base_url}{self.vision_endpoint}",
				json=payload,
				headers=headers,
			)
			response.raise_for_status()
			data = response.json()
			verdict = _pick_bool_payload(data)
			return bool(verdict)


def get_dify_client() -> MockDifyClient | DifyClient:
	if os.getenv("MEDIA_AI_USE_REAL_DIFY", "0") == "1":
		return DifyClient()
	return MockDifyClient()
