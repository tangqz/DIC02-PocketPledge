from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx


logger = logging.getLogger(__name__)

conversation_ids: dict[str, str] = {}

RETRYABLE_STATUS_CODES = {502, 503, 504}


def _pick_outputs_payload(payload: Any) -> dict[str, Any]:
	if isinstance(payload, dict):
		outputs = payload.get("outputs")
		if isinstance(outputs, dict):
			return outputs
		data = payload.get("data")
		if data is not None:
			return _pick_outputs_payload(data)
	return {}


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
		language_mode: str = "zh",
		character_id: str = "milly",
	) -> AsyncIterator[str]:
		_ = (session_id, language_mode, character_id)
		lower_text = user_text.lower()
		has_system_result = "[SYSTEM_RESULT:" in user_text

		if has_system_result:
			# Phase 2: substantive reply after system agent processing
			if "action=start" in lower_text:
				reply = "[encouraging]好的，计时器已经启动了，我们集中注意力！"
			elif "action=pause" in lower_text:
				if "approved=true" in lower_text:
					reply = "[neutral]好吧，去吧，记得快点回来。"
				else:
					reply = "[strict]这才刚开始多久，再坚持一下！"
			elif "action=resume" in lower_text:
				reply = "[encouraging]欢迎回来，继续加油！"
			elif "action=complete" in lower_text:
				reply = "[proud]辛苦了，今天的学习结束了。"
			elif "action=plan" in lower_text:
				reply = "[encouraging]计划已经更新好了，按这个来吧！"
			else:
				reply = "[neutral]好的，我已经处理完了。"
		elif any(keyword in user_text for keyword in ("看看", "看下", "帮我看", "分析一下")):
			# Phase 1: visual-context request → short transition + <<SYS>>
			reply = "[neutral]让我看看。<<SYS>>"
		elif any(keyword in user_text for keyword in ("开始", "暂停", "休息", "继续", "恢复", "结束", "停止", "计划", "安排")):
			# Phase 1: action detected → short transition + <<SYS>>
			reply = "[encouraging]好的稍等！<<SYS>>"
		else:
			# Simple chat — no system agent needed
			reply = "[encouraging]我在，继续专注当前任务。"

		if current_task and not has_system_result:
			if "<<SYS>>" not in reply:
				reply += f"[neutral]当前目标是{current_task}。"
		if images and not has_system_result:
			if "<<SYS>>" not in reply:
				reply += "[neutral]我会结合你刚刚提供的画面继续陪你。"

		for token in reply:
			await asyncio.sleep(0)
			yield token

	async def evaluate_vision(
		self,
		images: list[dict[str, Any]],
		current_task: str | None = None,
		session_id: str | None = None,
	) -> tuple[bool, str]:
		_ = (current_task, session_id)
		if not images:
			return False, ""

		for image in images:
			source = str(image.get("source", "")).lower()
			hint = str(image.get("hint", "")).lower()
			if any(keyword in hint for keyword in ("phone", "video", "game", "social")):
				return True, "mock: 发现违规关键字"
			if source == "screen" and len(str(image.get("data", ""))) < 128:
				return True, "mock: 屏幕数据异常"
		return False, ""

	async def evaluate_start_readiness(
		self,
		images: list[dict[str, Any]],
		current_task: str | None = None,
		session_id: str | None = None,
	) -> dict[str, Any]:
		_ = (current_task, session_id)
		has_camera = False
		has_screen = False
		screen_full = False
		for image in images:
			source = str(image.get("source", "")).lower()
			raw_metadata = image.get("metadata")
			metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
			if source == "camera":
				has_camera = True
			if source == "screen":
				has_screen = True
				if str(metadata.get("displaySurface", "")).lower() == "monitor":
					screen_full = True

		if not has_camera or not has_screen:
			return {
				"approved": False,
				"camera_ok": has_camera,
				"screen_ok": has_screen and screen_full,
				"reason": "还没同时拿到摄像头和全屏共享画面",
			}
		if not screen_full:
			return {
				"approved": False,
				"camera_ok": True,
				"screen_ok": False,
				"reason": "请改成整块屏幕的全屏共享",
			}
		return {
			"approved": True,
			"camera_ok": True,
			"screen_ok": True,
			"reason": "环境检查通过",
		}

	async def run_system_agent(
		self,
		session_id: str,
		inputs: dict[str, Any],
	) -> dict[str, Any]:
		user_text = str(inputs.get("user_text", ""))
		state = str(inputs.get("supervision_state", "setup"))
		current_task = str(inputs.get("current_task", "") or "完成当前学习任务")
		pause_requests_count = int(inputs.get("pause_requests_count", 0) or 0)
		focus_time_remaining = int(inputs.get("focus_time_remaining", 0) or 0)
		total_focus_seconds = int(inputs.get("total_focus_seconds", 0) or 0)
		lowered = user_text.lower()

		def minutes_from_text(default: int) -> int:
			import re
			match = re.search(r"(\d{1,3})\s*(分钟|分|min|mins|minute|minutes)", user_text, re.IGNORECASE)
			if match:
				return max(1, min(int(match.group(1)), 180))
			return default

		if any(keyword in user_text or keyword in lowered for keyword in ("看看", "看下", "帮我看", "分析一下")):
			sources: list[str] = []
			if any(keyword in user_text for keyword in ("桌面", "屏幕", "页面", "窗口", "代码", "文档", "应用")):
				sources.append("screen")
			if any(keyword in user_text for keyword in ("摄像头", "镜头", "我这边", "我本人", "环境", "样子", "状态")):
				sources.append("camera")
			if not sources:
				sources = ["screen", "camera"]
			return {
				"action": "none",
				"approved": True,
				"duration_seconds": 0,
				"pause_seconds": 0,
				"requires_capture": True,
				"capture_sources": sources,
				"system_events": [f"[SYSTEM_EVENT: VISUAL_CONTEXT_REQUESTED, SOURCES: {','.join(sources)}]"],
				"plan": None,
			}

		if any(keyword in user_text or keyword in lowered for keyword in ("结束", "停止", "不学了", "end", "stop", "finish")):
			return {
				"action": "complete",
				"approved": True,
				"duration_seconds": 0,
				"pause_seconds": 0,
				"requires_capture": False,
				"capture_sources": [],
				"system_events": ["[SYSTEM_EVENT: SESSION_COMPLETED, SOURCE: system_agent]"],
				"plan": None,
			}

		if any(keyword in user_text or keyword in lowered for keyword in ("继续", "恢复", "回来", "resume", "continue")):
			return {
				"action": "resume",
				"approved": True,
				"duration_seconds": 0,
				"pause_seconds": 0,
				"requires_capture": False,
				"capture_sources": [],
				"system_events": ["[SYSTEM_EVENT: PAUSE_RESUME_REQUESTED]"],
				"plan": None,
			}

		if any(keyword in user_text or keyword in lowered for keyword in ("暂停", "休息", "上厕所", "洗手间", "喝水", "太累", "pause", "break")):
			minutes = max(1, min(minutes_from_text(5), 10))
			elapsed_seconds = max(total_focus_seconds - focus_time_remaining, 0)
			urgent_reason = any(keyword in user_text for keyword in ("厕所", "洗手间", "头晕", "不舒服", "喝水", "restroom", "bathroom", "toilet"))
			approved = urgent_reason or elapsed_seconds >= 300 or pause_requests_count == 0
			return {
				"action": "pause",
				"approved": approved,
				"duration_seconds": 0,
				"pause_seconds": minutes * 60,
				"requires_capture": False,
				"capture_sources": [],
				"system_events": [
					f"[SYSTEM_EVENT: {'PAUSE_APPROVED' if approved else 'PAUSE_REJECTED'}, MINUTES: {minutes}]"
				],
				"plan": None,
			}

		if any(keyword in user_text or keyword in lowered for keyword in ("计划", "安排", "打算", "目标")):
			minutes = minutes_from_text(25)
			plan = {
				"tasks": [{"id": "t1", "title": current_task if current_task != "完成当前学习任务" else user_text.strip() or current_task, "completed": False, "estimatedMinutes": minutes}],
				"totalMinutes": minutes,
				"suggestedDuration": minutes * 60,
			}
			return {
				"action": "plan",
				"approved": True,
				"duration_seconds": 0,
				"pause_seconds": 0,
				"requires_capture": False,
				"capture_sources": [],
				"system_events": [f"[SYSTEM_EVENT: PLAN_UPDATED, TITLE: {plan['tasks'][0]['title']}, TOTAL_MINUTES: {minutes}]"],
				"plan": plan,
			}

		if any(keyword in user_text or keyword in lowered for keyword in ("开始", "开工", "进入监督", "start")):
			minutes = minutes_from_text(max(int(inputs.get("suggested_focus_seconds", 1500) or 1500) // 60, 1))
			return {
				"action": "start",
				"approved": True,
				"duration_seconds": minutes * 60,
				"pause_seconds": 0,
				"requires_capture": False,
				"capture_sources": [],
				"system_events": [f"[SYSTEM_EVENT: SESSION_START_REQUESTED, MINUTES: {minutes}]"],
				"plan": None,
			}

		return {
			"action": "none",
			"approved": True,
			"duration_seconds": 0,
			"pause_seconds": 0,
			"requires_capture": False,
			"capture_sources": [],
			"system_events": [],
			"plan": None,
		}


class DifyClient:
	"""Real Dify proxy with SSE chat support and blocking workflow support."""

	def __init__(self) -> None:
		self.base_url = os.getenv("DIFY_API_BASE", "").rstrip("/")
		self.chat_endpoint = os.getenv("DIFY_CHAT_ENDPOINT", "/v1/chat-messages")
		self.file_upload_endpoint = os.getenv("DIFY_FILE_UPLOAD_ENDPOINT", "/v1/files/upload")
		self.vision_endpoint = os.getenv("DIFY_VISION_ENDPOINT", "/v1/workflows/run")
		self.system_agent_endpoint = os.getenv("DIFY_SYSTEM_AGENT_ENDPOINT", "/v1/workflows/run")
		self.chat_api_key = os.getenv("DIFY_CHAT_API_KEY", "")
		self.vision_api_key = os.getenv("DIFY_VISION_API_KEY", self.chat_api_key)
		self.system_agent_api_key = os.getenv("DIFY_SYSTEM_AGENT_API_KEY", self.chat_api_key)
		self.timeout = float(os.getenv("MEDIA_AI_HTTP_TIMEOUT", "20"))
		self.system_agent_timeout = float(os.getenv("DIFY_SYSTEM_AGENT_TIMEOUT", "60"))
		self.retry_attempts = max(1, int(os.getenv("DIFY_HTTP_RETRY_ATTEMPTS", "2")))
		self.retry_backoff_seconds = float(os.getenv("DIFY_HTTP_RETRY_BACKOFF_SECONDS", "0.8"))

	def _should_retry(self, exc: Exception) -> bool:
		if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRYABLE_STATUS_CODES:
			return True
		if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)):
			return True
		return False

	async def _sleep_before_retry(self, attempt: int, endpoint: str, exc: Exception) -> None:
		delay = self.retry_backoff_seconds * attempt
		logger.warning("Dify request failed, retrying endpoint=%s attempt=%s delay=%.2fs error=%s", endpoint, attempt, delay, exc)
		await asyncio.sleep(delay)

	async def stream_chat(
		self,
		user_text: str,
		session_id: str,
		images: list[dict[str, Any]] | None = None,
		current_task: str | None = None,
		language_mode: str = "zh",
		character_id: str = "milly",
	) -> AsyncIterator[str]:
		if not self.base_url or not self.chat_api_key:
			raise RuntimeError("Missing Dify chat configuration")

		payload: dict[str, Any] = {
			"inputs": {
				"current_task": current_task or "",
				"language_mode": language_mode,
				"character_id": character_id,
			},
			"query": user_text,
			"response_mode": "streaming",
			"user": session_id,
		}
		conversation_id = conversation_ids.get(session_id)
		if conversation_id:
			payload["conversation_id"] = conversation_id
		headers = {
			"Authorization": f"Bearer {self.chat_api_key}",
			"Content-Type": "application/json",
			"Accept": "text/event-stream",
		}

		async with httpx.AsyncClient(timeout=self.timeout) as client:
			if images:
				uploaded_files = await self._upload_chat_images(client, session_id, images)
				if uploaded_files:
					payload["files"] = uploaded_files
			last_error: Exception | None = None
			for attempt in range(1, self.retry_attempts + 1):
				try:
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
							conversation_id = event.get("conversation_id")
							if isinstance(conversation_id, str) and conversation_id:
								conversation_ids[session_id] = conversation_id
							text = _pick_text_payload(event)
							if text:
								yield text
					return
				except Exception as exc:
					last_error = exc
					if attempt >= self.retry_attempts or not self._should_retry(exc):
						raise
					await self._sleep_before_retry(attempt, self.chat_endpoint, exc)

			if last_error is not None:
				raise last_error

	async def _upload_chat_images(
		self,
		client: httpx.AsyncClient,
		session_id: str,
		images: list[dict[str, Any]],
	) -> list[dict[str, str]]:
		uploaded_files: list[dict[str, str]] = []
		for index, image in enumerate(images):
			base64_data = str(image.get("data", ""))
			mime_type = str(image.get("mime_type", "image/jpeg"))
			source = str(image.get("source", "image"))
			if not base64_data:
				continue
			try:
				file_bytes = base64.b64decode(base64_data)
			except Exception:
				logger.warning("Failed to decode chat image payload for session %s", session_id)
				continue

			response = await client.post(
				f"{self.base_url}{self.file_upload_endpoint}",
				headers={"Authorization": f"Bearer {self.chat_api_key}"},
				data={"user": session_id},
				files={
					"file": (
						f"{source}-{index}.jpg",
						file_bytes,
						mime_type,
					)
				},
			)
			response.raise_for_status()
			result = response.json()
			upload_file_id = result.get("id")
			if isinstance(upload_file_id, str) and upload_file_id:
				uploaded_files.append(
					{
						"type": "image",
						"transfer_method": "local_file",
						"upload_file_id": upload_file_id,
					}
				)
		return uploaded_files

	async def evaluate_vision(
		self,
		images: list[dict[str, Any]],
		current_task: str | None = None,
		session_id: str | None = None,
	) -> bool:
		if not self.base_url or not self.vision_api_key:
			raise RuntimeError("Missing Dify vision configuration")

		user = session_id or "vision-anonymous"

		async with httpx.AsyncClient(timeout=self.timeout) as client:
			uploaded = await self._upload_vision_images(client, user, images)
			if not uploaded:
				logger.warning("No images uploaded for vision evaluation")
				return False

			payload: dict[str, Any] = {
				"inputs": {
					"current_task": current_task or "",
					"images": uploaded,
				},
				"response_mode": "blocking",
				"user": user,
			}
			headers = {
				"Authorization": f"Bearer {self.vision_api_key}",
				"Content-Type": "application/json",
			}
			response = await client.post(
				f"{self.base_url}{self.vision_endpoint}",
				json=payload,
				headers=headers,
			)
			response.raise_for_status()
			data = response.json()
			
			verdict = False
			reason = ""
			try:
				if "data" in data and isinstance(data["data"], dict) and "outputs" in data["data"]:
					text = (data["data"]["outputs"].get("text") or "").strip()
					# try to parse json from text
					import json
					# extract json
					import re
					match = re.search(r"\{.*\}", text, re.DOTALL)
					if match:
						parsed = json.loads(match.group(0))
						verdict = bool(parsed.get("is_distracted", False))
						reason = str(parsed.get("reason", ""))
				else:
					# Legacy fallback
					verdict = bool(_pick_bool_payload(data))
			except Exception as e:
				logger.warning("Failed to parse dify vision response: %s", e)
			
			return verdict, reason

	async def _upload_vision_images(
		self,
		client: httpx.AsyncClient,
		user: str,
		images: list[dict[str, Any]],
	) -> list[dict[str, str]]:
		"""Upload images for vision workflow and return Dify file references."""
		uploaded: list[dict[str, str]] = []
		for index, image in enumerate(images):
			base64_data = str(image.get("data", ""))
			mime_type = str(image.get("mime_type", "image/jpeg"))
			source = str(image.get("source", "image"))
			if not base64_data:
				continue
			try:
				file_bytes = base64.b64decode(base64_data)
			except Exception:
				logger.warning("Failed to decode vision image %d", index)
				continue
			response = await client.post(
				f"{self.base_url}{self.file_upload_endpoint}",
				headers={"Authorization": f"Bearer {self.vision_api_key}"},
				data={"user": user},
				files={"file": (f"{source}-{index}.jpg", file_bytes, mime_type)},
			)
			response.raise_for_status()
			result = response.json()
			upload_id = result.get("id")
			if isinstance(upload_id, str) and upload_id:
				uploaded.append({
					"type": "image",
					"transfer_method": "local_file",
					"upload_file_id": upload_id,
				})
		return uploaded

	async def run_system_agent(
		self,
		session_id: str,
		inputs: dict[str, Any],
	) -> dict[str, Any]:
		if not self.base_url or not self.system_agent_api_key:
			raise RuntimeError("Missing Dify system agent configuration")

		payload = {
			"inputs": inputs,
			"response_mode": "blocking",
			"user": session_id,
		}
		headers = {
			"Authorization": f"Bearer {self.system_agent_api_key}",
			"Content-Type": "application/json",
		}

		logger.info("calling Dify system workflow url=%s%s session_id=%s", self.base_url, self.system_agent_endpoint, session_id)
		async with httpx.AsyncClient(timeout=self.system_agent_timeout) as client:
			last_error: Exception | None = None
			for attempt in range(1, self.retry_attempts + 1):
				try:
					response = await client.post(
						f"{self.base_url}{self.system_agent_endpoint}",
						json=payload,
						headers=headers,
					)
					response.raise_for_status()
					logger.info("Dify system workflow response received, session_id=%s status=%s", session_id, response.status_code)
					return _pick_outputs_payload(response.json())
				except Exception as exc:
					last_error = exc
					if attempt >= self.retry_attempts or not self._should_retry(exc):
						raise
					await self._sleep_before_retry(attempt, self.system_agent_endpoint, exc)

			if last_error is not None:
				raise last_error
		return {}

	async def evaluate_start_readiness(
		self,
		images: list[dict[str, Any]],
		current_task: str | None = None,
		session_id: str | None = None,
	) -> dict[str, Any]:
		_ = current_task
		has_camera = any(str(image.get("source", "")).lower() == "camera" for image in images)
		screen_metadata = next(
			(
				image.get("metadata")
				for image in images
				if str(image.get("source", "")).lower() == "screen" and isinstance(image.get("metadata"), dict)
			),
			{},
		)
		screen_ok = str((screen_metadata or {}).get("displaySurface", "")).lower() == "monitor"
		if not has_camera or not screen_ok:
			return {
				"approved": False,
				"camera_ok": has_camera,
				"screen_ok": screen_ok,
				"reason": "请确保摄像头能拍到上半身，并且使用全屏共享后再开始",
			}
		return {
			"approved": True,
			"camera_ok": True,
			"screen_ok": True,
			"reason": "环境检查通过",
		}


def get_dify_client() -> MockDifyClient | DifyClient:
	"""Return the appropriate LLM client based on AGENT_BACKEND env var.

	Values: "local" | "dify" | "mock" (default).
	Legacy MEDIA_AI_USE_REAL_DIFY=1 is still respected as a fallback.
	"""
	backend = os.getenv("AGENT_BACKEND", "").strip().lower()
	if backend == "local":
		from app.agent.local_client import LocalLLMClient
		return LocalLLMClient()  # type: ignore[return-value]
	if backend == "dify":
		return DifyClient()
	if backend == "mock":
		return MockDifyClient()
	# Legacy fallback
	if os.getenv("MEDIA_AI_USE_REAL_DIFY", "0") == "1":
		return DifyClient()
	return MockDifyClient()
