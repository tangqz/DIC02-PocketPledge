"""Local LLM client using OpenAI-compatible API.

Implements the same interface as the runtime chat provider clients so it can be
swapped in via the AGENT_BACKEND environment variable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI

from app.agent.prompts import (
    PROFILE_MEMORY_EXTRACT_PROMPT,
    START_READINESS_PROMPT,
    SYSTEM_AGENT_PROMPT,
    VISION_EVALUATION_PROMPT,
    get_chat_system_prompt,
    get_character_card,
)
from app.agent.token_tracker import track_token_usage
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.business.models import SessionLocal
from app.business.crud import (
    get_user_profile_document,
    list_assessment_results,
    list_meal_journal_entries,
    list_mood_entries,
)

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 50
MAX_TOOL_ROUNDS = 8
LOG_TEXT_LIMIT = 300


def _truncate_text(value: Any, limit: int = LOG_TEXT_LIMIT) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _summarize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return _truncate_text(content)
    if isinstance(content, list):
        summary: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                summary.append(_truncate_text(item))
                continue
            item_type = item.get("type")
            if item_type == "text":
                summary.append(f"text={_truncate_text(item.get('text', ''))}")
            elif item_type == "image_url":
                summary.append("image=<base64>")
            else:
                summary.append(_truncate_text(item))
        return " | ".join(summary)
    return _truncate_text(content)


def _serialize_tool_call(tool_call: Any) -> dict[str, Any]:
    if isinstance(tool_call, dict):
        serialized = dict(tool_call)
    elif hasattr(tool_call, "model_dump"):
        serialized = cast(dict[str, Any], tool_call.model_dump(exclude_none=True))
    elif hasattr(tool_call, "to_dict"):
        serialized = cast(dict[str, Any], tool_call.to_dict())
    else:
        serialized = {}

    function = getattr(tool_call, "function", None)
    serialized["id"] = serialized.get("id") or getattr(tool_call, "id", "")
    serialized["type"] = (
        serialized.get("type") or getattr(tool_call, "type", "function") or "function"
    )

    function_payload = serialized.get("function")
    if not isinstance(function_payload, dict):
        function_payload = {}
    function_payload["name"] = (
        function_payload.get("name") or getattr(function, "name", "") or ""
    )
    function_payload["arguments"] = (
        function_payload.get("arguments")
        or getattr(function, "arguments", "{}")
        or "{}"
    )
    serialized["function"] = function_payload
    return serialized


def _serialize_assistant_message(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": getattr(message, "content", None) or "",
    }
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        payload["tool_calls"] = [
            _serialize_tool_call(tool_call) for tool_call in tool_calls
        ]
    return payload


# Cached AsyncOpenAI clients — reuse connections instead of creating per-request
_chat_client: AsyncOpenAI | None = None
_agent_client: AsyncOpenAI | None = None
_vision_client: AsyncOpenAI | None = None


def _get_chat_client() -> AsyncOpenAI:
    """OpenAI-compatible client for the Chat VTuber model (cached singleton)."""
    global _chat_client
    if _chat_client is None:
        _chat_client = AsyncOpenAI(
            api_key=os.getenv("LOCAL_CHAT_API_KEY", "sk-placeholder"),
            base_url=os.getenv("LOCAL_CHAT_API_BASE", "https://api.openai.com/v1"),
            timeout=float(os.getenv("LOCAL_CHAT_TIMEOUT", "30")),
        )
    return _chat_client


def _get_agent_client() -> AsyncOpenAI:
    """OpenAI-compatible client for the System Agent model (cached singleton)."""
    global _agent_client
    if _agent_client is None:
        _agent_client = AsyncOpenAI(
            api_key=os.getenv("LOCAL_AGENT_API_KEY")
            or os.getenv("LOCAL_CHAT_API_KEY", "sk-placeholder"),
            base_url=os.getenv("LOCAL_AGENT_API_BASE")
            or os.getenv("LOCAL_CHAT_API_BASE", "https://api.openai.com/v1"),
            timeout=float(
                os.getenv("LOCAL_AGENT_TIMEOUT") or os.getenv("LOCAL_CHAT_TIMEOUT", "60")
            ),
        )
    return _agent_client


def _get_vision_client() -> AsyncOpenAI:
    """OpenAI-compatible client for the Vision / Supervision model (cached singleton)."""
    global _vision_client
    if _vision_client is None:
        _vision_client = AsyncOpenAI(
            api_key=os.getenv("LOCAL_VISION_API_KEY", "sk-placeholder"),
            base_url=os.getenv("LOCAL_VISION_API_BASE", "https://api.openai.com/v1"),
            timeout=float(os.getenv("LOCAL_VISION_TIMEOUT", "30")),
        )
    return _vision_client


# ⚡ Bolt: execute synchronous database I/O in a separate thread to avoid blocking the main asyncio event loop during chat streaming
async def _load_profile_content(user_id: str) -> str:
    try:
        uid = int(user_id)
    except ValueError:
        return ""

    def _sync_load() -> str:
        db = SessionLocal()
        try:
            result = get_user_profile_document(db, uid)
            return result.get("content", "")
        except Exception:
            return ""
        finally:
            db.close()

    return await asyncio.to_thread(_sync_load)


async def _load_recent_behavior_summary(user_id: str, language_mode: str) -> str:
    try:
        uid = int(user_id)
    except ValueError:
        return ""

    def _sync_load() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        db = SessionLocal()
        try:
            moods = list_mood_entries(db, uid, limit=8, days=14).get("items", [])
            meals = list_meal_journal_entries(db, uid, limit=6, days=14).get("items", [])
            assessments = list_assessment_results(db, uid, limit=6, days=30).get(
                "items", []
            )
            mood_items = [item for item in moods if isinstance(item, dict)]
            meal_items = [item for item in meals if isinstance(item, dict)]
            assessment_items = [
                item for item in assessments if isinstance(item, dict)
            ]
            return mood_items, meal_items, assessment_items
        except Exception:
            return [], [], []
        finally:
            db.close()

    mood_items, meal_items, assessment_items = await asyncio.to_thread(_sync_load)
    is_en = language_mode.strip().lower() == "en"

    if not mood_items and not meal_items and not assessment_items:
        return ""

    lines: list[str] = []
    if is_en:
        lines.append("=== Recent Mood & Meal Context ===")
        if mood_items:
            latest = mood_items[0]
            lines.append(
                f"Latest mood: {latest.get('emotion', 'neutral')} ({latest.get('intensity', 1)}/5)"
            )
        if meal_items:
            latest_meal = str(meal_items[0].get("meal_info") or "").strip()
            if latest_meal:
                lines.append(f"Latest meal note: {latest_meal[:60]}")
        if assessment_items:
            latest_assessment = assessment_items[0]
            lines.append(
                f"Latest screening: {latest_assessment.get('assessment_type', 'assessment')}="
                f"{latest_assessment.get('score', 0)} ({latest_assessment.get('severity', 'unknown')})"
            )
    else:
        lines.append("═══ 最近情绪与饮食上下文 ═══")
        if mood_items:
            latest = mood_items[0]
            lines.append(
                f"最近一次情绪：{latest.get('emotion', 'neutral')}（{latest.get('intensity', 1)}/5）"
            )
        if meal_items:
            latest_meal = str(meal_items[0].get("meal_info") or "").strip()
            if latest_meal:
                lines.append(f"最近饮食记录：{latest_meal[:60]}")
        if assessment_items:
            latest_assessment = assessment_items[0]
            lines.append(
                f"最近一次自测：{latest_assessment.get('assessment_type', 'assessment')}="
                f"{latest_assessment.get('score', 0)}（{latest_assessment.get('severity', 'unknown')}）"
            )

    return "\n".join(lines)


def _build_chat_system_prompt(
    profile_content: str,
    current_task: str | None,
    focus_status: str | None,
    language_mode: str,
) -> str:
    normalized_lang = language_mode.strip().lower()
    now_local = datetime.now().astimezone()
    parts = [get_chat_system_prompt(normalized_lang)]
    if normalized_lang == "en":
        parts.append(
            "\n=== Time Context ==="
            f"\nCurrent local time: {now_local.isoformat()}"
            f"\nCurrent local date: {now_local.date().isoformat()}"
            f"\nTimezone: {now_local.tzname() or 'local'}"
        )
        if profile_content:
            parts.append(f"\n=== User Profile ===\n{profile_content}")
        if current_task:
            parts.append(f"\nCurrent task: {current_task}")
        if focus_status:
            parts.append(f"\nCurrent focus status: {focus_status}")
    else:
        parts.append(
            "\n═══ 时间上下文 ═══"
            f"\n当前本地时间：{now_local.isoformat()}"
            f"\n当前本地日期：{now_local.date().isoformat()}"
            f"\n时区：{now_local.tzname() or 'local'}"
        )
        if profile_content:
            parts.append(f"\n═══ 用户画像 ═══\n{profile_content}")
        if current_task:
            parts.append(f"\n当前学习任务：{current_task}")
        if focus_status:
            parts.append(f"\n当前专注状态：{focus_status}")
    return "\n".join(parts)


def _build_language_block(language_mode: str) -> str:
    normalized = language_mode.strip().lower()
    if normalized == "en":
        return (
            "\nLanguage lock: en. You must respond in fluent natural English only."
            " Never output Chinese characters unless directly quoting the user."
        )
    return "\n当前语言模式：zh。你必须只用自然中文回复。"


def _build_runtime_chat_system_prompt(
    profile_content: str,
    current_task: str | None,
    focus_status: str | None,
    language_mode: str,
    character_id: str,
) -> str:
    base = _build_chat_system_prompt(
        profile_content,
        current_task,
        focus_status,
        language_mode,
    )
    character_card = get_character_card(character_id, language_mode)
    return f"{character_card}\n{base}{_build_language_block(language_mode)}"


def _build_user_content(
    user_text: str,
    images: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    """Build the user message content, with optional vision images."""
    if not images:
        return user_text
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for img in images:
        base64_data = str(img.get("data", ""))
        mime_type = str(img.get("mime_type", "image/jpeg"))
        if base64_data:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
                }
            )
    return content


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


class LocalLLMClient:
    """Local LLM client implementing the runtime provider interface."""

    def __init__(self) -> None:
        self._chat_model = os.getenv("LOCAL_CHAT_MODEL", "")
        self._system_agent_model = os.getenv("LOCAL_AGENT_MODEL", self._chat_model)
        self._vision_model = os.getenv("LOCAL_VISION_MODEL", self._chat_model)
        self._temperature_chat = float(os.getenv("LOCAL_CHAT_TEMPERATURE", "0.55"))
        self._temperature_agent = float(
            os.getenv(
                "LOCAL_AGENT_TEMPERATURE", os.getenv("LOCAL_CHAT_TEMPERATURE", "0.1")
            )
        )
        # Thinking config — chat (Gemini) deliberately left unconfigured = off
        self._agent_enable_thinking = os.getenv(
            "LOCAL_AGENT_ENABLE_THINKING", "true"
        ).lower() in ("true", "1", "yes")
        self._agent_reasoning_effort = (
            os.getenv("LOCAL_AGENT_REASONING_EFFORT", "").strip().lower()
        )
        self._agent_thinking_budget = int(os.getenv("LOCAL_AGENT_THINKING_BUDGET", "0"))
        self._vision_enable_thinking = os.getenv(
            "LOCAL_VISION_ENABLE_THINKING", "true"
        ).lower() in ("true", "1", "yes")
        self._vision_thinking_budget = int(
            os.getenv("LOCAL_VISION_THINKING_BUDGET", "1024")
        )
        # Per-session conversation history
        self._histories: dict[str, list[dict[str, Any]]] = {}

    def _build_system_agent_request_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self._agent_reasoning_effort in {"low", "medium", "high"}:
            options["reasoning_effort"] = self._agent_reasoning_effort
            return options

        if self._agent_enable_thinking:
            extra_body: dict[str, Any] = {"enable_thinking": True}
            if self._agent_thinking_budget > 0:
                extra_body["thinking_budget"] = self._agent_thinking_budget
            options["extra_body"] = extra_body
        return options

    def _get_history(self, session_id: str) -> list[dict[str, Any]]:
        if session_id not in self._histories:
            self._histories[session_id] = []
        return self._histories[session_id]

    def _trim_history(self, session_id: str) -> None:
        history = self._histories.get(session_id)
        if history and len(history) > MAX_HISTORY_MESSAGES:
            self._histories[session_id] = history[-MAX_HISTORY_MESSAGES:]

    async def stream_chat(
        self,
        user_text: str,
        session_id: str,
        images: list[dict[str, Any]] | None = None,
        current_task: str | None = None,
        focus_status: str | None = None,
        language_mode: str = "zh",
        character_id: str = "milly",
    ) -> AsyncIterator[str]:
        """Stream chat response tokens using the shared provider interface."""
        profile_content, behavior_context = await asyncio.gather(
            _load_profile_content(session_id),
            _load_recent_behavior_summary(session_id, language_mode),
        )
        combined_profile = profile_content
        if behavior_context:
            combined_profile = (
                f"{profile_content}\n\n{behavior_context}"
                if profile_content
                else behavior_context
            )
        system_prompt = _build_runtime_chat_system_prompt(
            profile_content=combined_profile,
            current_task=current_task,
            focus_status=focus_status,
            language_mode=language_mode,
            character_id=character_id,
        )
        history = self._get_history(session_id)

        user_content = _build_user_content(user_text, images)
        user_message: dict[str, Any] = {"role": "user", "content": user_content}

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
            user_message,
        ]

        collected_text = ""
        try:
            logger.info(
                "local chat api request session_id=%s model=%s current_task=%s images=%s lang=%s character=%s user=%s",
                session_id,
                self._chat_model,
                _truncate_text(current_task or ""),
                len(images or []),
                language_mode,
                character_id,
                _truncate_text(user_text),
            )
            stream = await _get_chat_client().chat.completions.create(
                model=self._chat_model,
                messages=cast(Any, messages),
                temperature=self._temperature_chat,
                stream=True,
                max_tokens=256,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        collected_text += delta.content
                        yield delta.content
                if getattr(chunk, "usage", None):
                    track_token_usage(self._chat_model, chunk.usage, session_id)

            logger.info(
                "local chat api response session_id=%s model=%s text=%s",
                session_id,
                self._chat_model,
                _truncate_text(collected_text),
            )
        except Exception:
            logger.exception("local chat stream failed, session_id=%s", session_id)
            raise
        finally:
            # Always record the exchange in history (even partial)
            history.append({"role": "user", "content": user_text})
            if collected_text:
                history.append({"role": "assistant", "content": collected_text})
            self._trim_history(session_id)

    async def evaluate_vision(
        self,
        images: list[dict[str, Any]],
        current_task: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate user emotion from camera images using a vision model."""
        _default = {"emotion": "neutral", "intensity": 1, "cues": "", "suggestion": ""}
        if not images:
            return _default

        prompt = VISION_EVALUATION_PROMPT

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        # Parse and concatenate multiple images if present
        import io
        from PIL import Image
        import base64

        pil_images = []
        for img in images:
            base64_data = str(img.get("data", ""))
            if base64_data:
                try:
                    img_data = base64.b64decode(base64_data)
                    pil_img = Image.open(io.BytesIO(img_data)).convert("RGB")
                    pil_images.append(pil_img)
                except Exception as e:
                    logger.warning("Failed to decode image: %s", e)

        if pil_images:
            # Concatenate horizontally
            widths, heights = zip(*(i.size for i in pil_images))
            total_width = sum(widths)
            max_height = max(heights)

            new_im = Image.new("RGB", (total_width, max_height))
            x_offset = 0
            for im in pil_images:
                new_im.paste(im, (x_offset, 0))
                x_offset += im.size[0]

            # Save for debugging
            debug_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "latest_vision_input.jpg"
            )
            try:
                new_im.save(debug_path)
            except Exception as e:
                logger.warning("Failed to save debug image: %s", e)

            # Compress and encode
            buffered = io.BytesIO()
            new_im.save(buffered, format="JPEG", quality=80)
            final_b64 = base64.b64encode(buffered.getvalue()).decode()

            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{final_b64}"},
                }
            )

        vision_extra: dict[str, Any] = {"enable_thinking": self._vision_enable_thinking}
        if self._vision_enable_thinking:
            vision_extra["thinking_budget"] = self._vision_thinking_budget

        try:
            logger.info(
                "local vision api request session_id=%s model=%s current_task=%s images=%s",
                session_id,
                self._vision_model,
                _truncate_text(current_task or ""),
                len(images),
            )
            response = await _get_vision_client().chat.completions.create(
                model=self._vision_model,
                messages=cast(Any, [{"role": "user", "content": content}]),
                temperature=0,
                max_tokens=64,
                extra_body=vision_extra,
            )
            if getattr(response, "usage", None):
                track_token_usage(self._vision_model, response.usage, session_id)

            text = (response.choices[0].message.content or "").strip()
            text = _strip_code_fences(text)

            import re

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    result = {
                        "emotion": str(data.get("emotion", "neutral")),
                        "intensity": int(data.get("intensity", 1)),
                        "cues": str(data.get("cues", "")),
                        "suggestion": str(data.get("suggestion", "")),
                    }
                except (json.JSONDecodeError, ValueError):
                    logger.warning("Failed to parse vision response as JSON: %s", text)
                    result = _default
            else:
                logger.warning("No JSON found in vision response: %s", text)
                result = _default

            logger.info(
                "local vision api response session_id=%s model=%s text=%s",
                session_id,
                self._vision_model,
                _truncate_text(text),
            )
            return result
        except Exception:
            logger.exception("local vision evaluation failed")
            return _default

    async def evaluate_start_readiness(
        self,
        images: list[dict[str, Any]],
        current_task: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not images:
            return {
                "approved": False,
                "camera_ok": False,
                "screen_ok": False,
                "reason": "还没拿到摄像头和屏幕画面",
            }

        metadata_lines: list[str] = []
        for img in images:
            source = str(img.get("source", "image"))
            raw_metadata = img.get("metadata")
            metadata: dict[str, Any] = (
                raw_metadata if isinstance(raw_metadata, dict) else {}
            )
            width = metadata.get("width")
            height = metadata.get("height")
            display_surface = metadata.get("displaySurface")
            facing_mode = metadata.get("facingMode")
            pieces = [f"source={source}"]
            if width and height:
                pieces.append(f"size={width}x{height}")
            if display_surface:
                pieces.append(f"displaySurface={display_surface}")
            if facing_mode:
                pieces.append(f"facingMode={facing_mode}")
            metadata_lines.append(", ".join(pieces))

        prompt = START_READINESS_PROMPT
        if current_task:
            prompt += f"\n当前任务：{current_task}"
        if metadata_lines:
            prompt += "\n画面元数据：\n" + "\n".join(metadata_lines)

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            base64_data = str(img.get("data", ""))
            mime_type = str(img.get("mime_type", "image/jpeg"))
            if base64_data:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
                    }
                )

        vision_extra: dict[str, Any] = {"enable_thinking": self._vision_enable_thinking}
        if self._vision_enable_thinking:
            vision_extra["thinking_budget"] = self._vision_thinking_budget

        try:
            logger.info(
                "local start-readiness request session_id=%s model=%s current_task=%s images=%s",
                session_id,
                self._vision_model,
                _truncate_text(current_task or ""),
                len(images),
            )

            max_attempts = 2
            last_error: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    response = await _get_vision_client().chat.completions.create(
                        model=self._vision_model,
                        messages=cast(Any, [{"role": "user", "content": content}]),
                        temperature=0,
                        max_tokens=160,
                        extra_body=vision_extra,
                    )
                    if getattr(response, "usage", None):
                        track_token_usage(self._vision_model, response.usage, session_id)

                    text = _strip_code_fences(
                        (response.choices[0].message.content or "").strip()
                    )
                    # Try direct parse first, then extract JSON object from text
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
                        if json_match:
                            data = json.loads(json_match.group())
                        else:
                            raise
                    if not isinstance(data, dict):
                        raise ValueError("start readiness response is not a JSON object")
                    result = {
                        "approved": bool(data.get("approved", False)),
                        "camera_ok": bool(data.get("camera_ok", False)),
                        "screen_ok": bool(data.get("screen_ok", False)),
                        "reason": str(data.get("reason", "环境检查未通过") or "环境检查未通过"),
                    }
                    logger.info(
                        "local start-readiness response session_id=%s model=%s text=%s",
                        session_id,
                        self._vision_model,
                        _truncate_text(text),
                    )
                    return result
                except (json.JSONDecodeError, ValueError, KeyError) as parse_err:
                    last_error = parse_err
                    logger.warning(
                        "start-readiness JSON parse failed (attempt %d/%d): %s",
                        attempt + 1, max_attempts, parse_err,
                    )
                    continue

            logger.error("start-readiness exhausted %d attempts", max_attempts)
            raise last_error or ValueError("JSON parse failed")  # noqa: TRY301
        except Exception:
            logger.exception("local start readiness evaluation failed")
            return {
                "approved": False,
                "camera_ok": False,
                "screen_ok": False,
                "reason": "环境检查失败，请重新共享画面后再试",
            }

    async def run_system_agent(
        self,
        session_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the system agent with function calling, returning structured outputs."""

        try:
            user_id = int(session_id)
        except ValueError:
            return {"action": "none", "approved": False, "error": "invalid session_id"}

        context_text = self._format_system_agent_context(inputs)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_AGENT_PROMPT},
            {"role": "user", "content": context_text},
        ]
        logger.info(
            "local system api request session_id=%s model=%s context=%s",
            session_id,
            self._system_agent_model,
            _truncate_text(context_text),
        )

        for _round in range(MAX_TOOL_ROUNDS):
            try:
                request_options = self._build_system_agent_request_options()
                response = await _get_agent_client().chat.completions.create(
                    model=self._system_agent_model,
                    messages=cast(Any, messages),
                    temperature=self._temperature_agent,
                    tools=cast(Any, TOOL_DEFINITIONS),
                    tool_choice="auto",
                    max_tokens=1024,
                    **request_options,
                )
            except Exception:
                logger.exception("local system agent LLM call failed, round=%d", _round)
                raise

            if getattr(response, "usage", None):
                track_token_usage(self._system_agent_model, response.usage, session_id)

            choice = response.choices[0]

            # If the model wants to call tools, execute them and continue
            if choice.message.tool_calls:
                messages.append(_serialize_assistant_message(choice.message))
                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name  # type: ignore[union-attr]
                    try:
                        fn_args = json.loads(tool_call.function.arguments)  # type: ignore[union-attr]
                    except json.JSONDecodeError:
                        fn_args = {}
                    logger.info(
                        "system agent tool call: %s(%s) user_id=%s",
                        fn_name,
                        fn_args,
                        user_id,
                    )
                    result_str = execute_tool(fn_name, fn_args, user_id)
                    messages.append(
                        {
                            "role": "tool",
                            "name": fn_name,
                            "tool_call_id": tool_call.id,
                            "content": result_str,
                        }
                    )
                continue

            # No tool calls — parse the final text as JSON
            raw_text = (choice.message.content or "").strip()
            logger.info(
                "local system api response session_id=%s model=%s round=%s text=%s",
                session_id,
                self._system_agent_model,
                _round,
                _truncate_text(raw_text),
            )
            return self._parse_agent_json(raw_text)

        # Exhausted tool rounds
        logger.warning(
            "system agent exceeded max tool rounds, session_id=%s", session_id
        )
        return {"action": "none", "approved": False, "system_events": []}

    def _format_system_agent_context(self, inputs: dict[str, Any]) -> str:
        now_local = datetime.now().astimezone()
        recent_moods = json.dumps(inputs.get("recent_moods", []), ensure_ascii=False)
        recent_meals = json.dumps(inputs.get("recent_meals", []), ensure_ascii=False)
        recent_assessments = json.dumps(
            inputs.get("recent_assessments", []), ensure_ascii=False
        )
        lines = [
            f"current_time_local: {now_local.isoformat()}",
            f"current_date_local: {now_local.date().isoformat()}",
            f"timezone: {now_local.tzname() or 'local'}",
            f"user_text: {inputs.get('user_text', '')}",
            f"chat_history:\n{inputs.get('chat_history', '')}",
            f"language_mode: {inputs.get('language_mode', 'zh')}",
            f"character_id: {inputs.get('character_id', 'milly')}",
            f"recent_mood_summary: {inputs.get('recent_mood_summary', '')}",
            f"recent_meal_summary: {inputs.get('recent_meal_summary', '')}",
            f"recent_assessment_summary: {inputs.get('recent_assessment_summary', '')}",
            f"recent_moods: {recent_moods}",
            f"recent_meals: {recent_meals}",
            f"recent_assessments: {recent_assessments}",
            f"is_bankrupt: {inputs.get('is_bankrupt', 'false')}",
        ]
        return "\n".join(lines)

    def _parse_agent_json(self, raw_text: str) -> dict[str, Any]:
        cleaned = _strip_code_fences(raw_text)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from within the text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

        logger.warning("failed to parse system agent JSON: %s", raw_text[:200])
        return {"action": "none", "approved": False, "system_events": []}

    async def extract_profile_memories(
        self,
        session_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract stable profile memories from one rotated chat batch."""
        rotated_chat = str(inputs.get("rotated_chat", "")).strip()
        if not rotated_chat:
            return {
                "should_update": False,
                "memory_lines": [],
                "reason": "empty rotated chat",
            }

        existing_profile = str(inputs.get("existing_profile", "")).strip()
        context_text = (
            f"rotated_chat:\n{rotated_chat}\n\n"
            f"existing_profile:\n{existing_profile}\n"
        )

        try:
            response = await _get_agent_client().chat.completions.create(
                model=self._system_agent_model,
                messages=cast(
                    Any,
                    [
                        {"role": "system", "content": PROFILE_MEMORY_EXTRACT_PROMPT},
                        {"role": "user", "content": context_text},
                    ],
                ),
                temperature=0.1,
                max_tokens=512,
            )
            raw_text = (response.choices[0].message.content or "").strip()
            parsed = self._parse_agent_json(raw_text)
            memory_lines = parsed.get("memory_lines")
            if not isinstance(memory_lines, list):
                memory_lines = []
            normalized_lines = [
                str(line).strip()
                for line in memory_lines
                if str(line).strip()
            ][:3]
            return {
                "should_update": bool(parsed.get("should_update", False))
                and bool(normalized_lines),
                "memory_lines": normalized_lines,
                "reason": str(parsed.get("reason", "") or ""),
            }
        except Exception:
            logger.exception(
                "local profile memory extraction failed, session_id=%s", session_id
            )
            return {
                "should_update": False,
                "memory_lines": [],
                "reason": "extract failed",
            }
