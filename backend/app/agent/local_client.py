"""Local LLM client using OpenAI-compatible API.

Implements the same interface as MockDifyClient / DifyClient so it can be
swapped in via the AGENT_BACKEND environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI

from app.agent.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_AGENT_PROMPT, VISION_EVALUATION_PROMPT
from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.business.models import SessionLocal
from app.business.crud import get_user_profile_document

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 40
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
    function = getattr(tool_call, "function", None)
    return {
        "id": getattr(tool_call, "id", ""),
        "type": getattr(tool_call, "type", "function") or "function",
        "function": {
            "name": getattr(function, "name", "") or "",
            "arguments": getattr(function, "arguments", "{}") or "{}",
        },
    }


def _serialize_assistant_message(message: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": getattr(message, "content", None) or "",
    }
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        payload["tool_calls"] = [_serialize_tool_call(tool_call) for tool_call in tool_calls]
    return payload


def _get_chat_client() -> AsyncOpenAI:
    """OpenAI-compatible client for the Chat VTuber model."""
    return AsyncOpenAI(
        api_key=os.getenv("LOCAL_CHAT_API_KEY", "sk-placeholder"),
        base_url=os.getenv("LOCAL_CHAT_API_BASE", "https://api.openai.com/v1"),
        timeout=float(os.getenv("LOCAL_CHAT_TIMEOUT", "30")),
    )


def _get_agent_client() -> AsyncOpenAI:
    """OpenAI-compatible client for the System Agent model."""
    return AsyncOpenAI(
        api_key=os.getenv("LOCAL_AGENT_API_KEY", "sk-placeholder"),
        base_url=os.getenv("LOCAL_AGENT_API_BASE", "https://api.openai.com/v1"),
        timeout=float(os.getenv("LOCAL_AGENT_TIMEOUT", "60")),
    )


def _get_vision_client() -> AsyncOpenAI:
    """OpenAI-compatible client for the Vision / Supervision model."""
    return AsyncOpenAI(
        api_key=os.getenv("LOCAL_VISION_API_KEY", "sk-placeholder"),
        base_url=os.getenv("LOCAL_VISION_API_BASE", "https://api.openai.com/v1"),
        timeout=float(os.getenv("LOCAL_VISION_TIMEOUT", "30")),
    )


def _load_profile_content(user_id: str) -> str:
    try:
        uid = int(user_id)
    except ValueError:
        return ""
    db = SessionLocal()
    try:
        result = get_user_profile_document(db, uid)
        return result.get("content", "")
    except Exception:
        return ""
    finally:
        db.close()


def _build_chat_system_prompt(profile_content: str, current_task: str | None) -> str:
    parts = [CHAT_SYSTEM_PROMPT]
    if profile_content:
        parts.append(f"\n═══ 用户画像 ═══\n{profile_content}")
    if current_task:
        parts.append(f"\n当前学习任务：{current_task}")
    return "\n".join(parts)


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
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
            })
    return content


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


class LocalLLMClient:
    """Local LLM client implementing the same interface as DifyClient."""

    def __init__(self) -> None:
        self._chat_model = os.getenv("LOCAL_CHAT_MODEL", "")
        self._system_agent_model = os.getenv("LOCAL_AGENT_MODEL", self._chat_model)
        self._vision_model = os.getenv("LOCAL_VISION_MODEL", self._chat_model)
        self._temperature_chat = float(os.getenv("LOCAL_CHAT_TEMPERATURE", "0.55"))
        self._temperature_agent = float(os.getenv("LOCAL_AGENT_TEMPERATURE", "0.1"))
        # Thinking config — chat (Gemini) deliberately left unconfigured = off
        self._agent_enable_thinking = os.getenv("LOCAL_AGENT_ENABLE_THINKING", "true").lower() in ("true", "1", "yes")
        self._vision_enable_thinking = os.getenv("LOCAL_VISION_ENABLE_THINKING", "true").lower() in ("true", "1", "yes")
        self._vision_thinking_budget = int(os.getenv("LOCAL_VISION_THINKING_BUDGET", "1024"))
        # Per-session conversation history
        self._histories: dict[str, list[dict[str, Any]]] = {}

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
    ) -> AsyncIterator[str]:
        """Stream chat response tokens, matching DifyClient.stream_chat interface."""
        profile_content = _load_profile_content(session_id)
        system_prompt = _build_chat_system_prompt(profile_content, current_task)
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
                "local chat api request session_id=%s model=%s current_task=%s images=%s user=%s",
                session_id,
                self._chat_model,
                _truncate_text(current_task or ""),
                len(images or []),
                _truncate_text(user_text),
            )
            stream = await _get_chat_client().chat.completions.create(
                model=self._chat_model,
                messages=cast(Any, messages),
                temperature=self._temperature_chat,
                stream=True,
                max_tokens=256,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    collected_text += delta.content
                    yield delta.content
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
    ) -> bool:
        """Evaluate whether the user is distracted using a vision model."""
        if not images:
            return False

        prompt = VISION_EVALUATION_PROMPT.format(current_task=current_task or "学习")

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            base64_data = str(img.get("data", ""))
            mime_type = str(img.get("mime_type", "image/jpeg"))
            if base64_data:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
                })

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
            text = (response.choices[0].message.content or "").strip()
            text = _strip_code_fences(text)
            data = json.loads(text)
            logger.info(
                "local vision api response session_id=%s model=%s text=%s",
                session_id,
                self._vision_model,
                _truncate_text(text),
            )
            return bool(data.get("is_distracted", False))
        except Exception:
            logger.exception("local vision evaluation failed")
            return False

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
                response = await _get_agent_client().chat.completions.create(
                    model=self._system_agent_model,
                    messages=cast(Any, messages),
                    temperature=self._temperature_agent,
                    tools=cast(Any, TOOL_DEFINITIONS),
                    tool_choice="auto",
                    max_tokens=1024,
                    extra_body={"enable_thinking": self._agent_enable_thinking},
                )
            except Exception:
                logger.exception("local system agent LLM call failed, round=%d", _round)
                raise

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
                        fn_name, fn_args, user_id,
                    )
                    result_str = execute_tool(fn_name, fn_args, user_id)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })
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
        logger.warning("system agent exceeded max tool rounds, session_id=%s", session_id)
        return {"action": "none", "approved": False, "system_events": []}

    def _format_system_agent_context(self, inputs: dict[str, Any]) -> str:
        lines = [
            f"user_text: {inputs.get('user_text', '')}",
            f"chat_history:\n{inputs.get('chat_history', '')}",
            f"supervision_state: {inputs.get('supervision_state', 'setup')}",
            f"current_task: {inputs.get('current_task', '')}",
            f"total_focus_seconds: {inputs.get('total_focus_seconds', 0)}",
            f"focus_time_remaining: {inputs.get('focus_time_remaining', 0)}",
            f"suggested_focus_seconds: {inputs.get('suggested_focus_seconds', 0)}",
            f"pause_remaining_seconds: {inputs.get('pause_remaining_seconds', 0)}",
            f"pause_requests_count: {inputs.get('pause_requests_count', 0)}",
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
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("failed to parse system agent JSON: %s", raw_text[:200])
        return {"action": "none", "approved": False, "system_events": []}
