from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _truncate(text: str, max_len: int = 220) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _infer_emotion_from_text(text: str) -> tuple[str, int]:
    lowered = text.lower()
    if _contains_any(lowered, ["开心", "高兴", "快乐", "happy", "glad", "excited"]):
        return "happy", 3
    if _contains_any(lowered, ["难过", "伤心", "低落", "sad", "down"]):
        return "sad", 4
    if _contains_any(lowered, ["焦虑", "紧张", "anxious", "anxiety", "panic"]):
        return "anxious", 4
    if _contains_any(lowered, ["压力", "崩溃", "stressed", "overwhelmed"]):
        return "stressed", 4
    if _contains_any(lowered, ["生气", "愤怒", "angry", "mad"]):
        return "angry", 3
    if _contains_any(lowered, ["累", "困", "疲惫", "tired", "sleepy", "exhausted"]):
        return "tired", 3
    if _contains_any(lowered, ["平静", "calm", "ok", "还好", "一般"]):
        return "calm", 2
    return "neutral", 2


class MockAgentClient:
    """Deterministic fallback client for local offline verification."""

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
        _ = (session_id, focus_status, character_id)
        is_en = language_mode.strip().lower() == "en"
        lowered = user_text.lower()

        if "[system_result:" in lowered:
            if "mood_recorded" in lowered:
                reply = (
                    "[encouraging]Nice work logging your feeling. That small step really matters."
                    if is_en
                    else "[encouraging]你把心情认真记下来了，这一步很了不起。"
                )
            elif "profile_noted" in lowered or "profile_updated" in lowered:
                reply = (
                    "[happy]Got it. I will remember this about you."
                    if is_en
                    else "[happy]收到啦，这条我会记住。"
                )
            elif "reward_granted" in lowered:
                reply = (
                    "[proud]You earned points today. Keep going, one gentle step at a time."
                    if is_en
                    else "[proud]你又获得积分啦，继续稳稳向前。"
                )
            elif "system_agent_error" in lowered:
                reply = (
                    "[encouraging]I hit a temporary issue, but I am still here with you."
                    if is_en
                    else "[encouraging]刚刚系统有点小问题，不过我还在陪你。"
                )
            else:
                reply = (
                    "[neutral]Done. I have handled that for you."
                    if is_en
                    else "[neutral]好啦，这件事我已经帮你处理了。"
                )
        elif _contains_any(
            user_text,
            [
                "看我",
                "看看我",
                "表情",
                "状态",
                "camera",
                "look at me",
                "how do i look",
            ],
        ):
            reply = (
                "[neutral]Sure, let me take a quick look.<<CAPTURE>>"
                if is_en
                else "[neutral]好，我看你一下。<<CAPTURE>>"
            )
        elif _contains_any(
            user_text,
            [
                "记录",
                "记一下",
                "心情",
                "情绪",
                "mood",
                "log",
                "feeling",
                "今天吃",
                "饮食",
                "meal",
                "ate",
            ],
        ):
            reply = (
                "[encouraging]Okay, I will record it for you.<<SYS>>"
                if is_en
                else "[encouraging]好，我来帮你记下来。<<SYS>>"
            )
        else:
            reply = (
                "[encouraging]I am here with you. We can take this one step at a time."
                if is_en
                else "[encouraging]我在呢，我们一步一步来。"
            )

        if images and "<<" not in reply:
            reply += (
                "[neutral] I will also consider what I just saw."
                if is_en
                else "[neutral]我也会结合刚刚看到的画面。"
            )
        if current_task and "<<" not in reply:
            reply += (
                f"[neutral] Current topic: {current_task}."
                if is_en
                else f"[neutral]当前话题是：{current_task}。"
            )

        for token in reply:
            await asyncio.sleep(0)
            yield token

    async def evaluate_vision(
        self,
        images: list[dict[str, Any]],
        current_task: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        _ = (current_task, session_id)
        if not images:
            return {
                "emotion": "neutral",
                "intensity": 1,
                "cues": "",
                "suggestion": "",
            }

        hint_blob = " ".join(
            str(image.get("hint", "")) + " " + str(image.get("metadata", {}))
            for image in images
        ).lower()

        if _contains_any(hint_blob, ["smile", "happy", "开心", "放松"]):
            return {
                "emotion": "happy",
                "intensity": 3,
                "cues": "mouth corners lifted, overall relaxed",
                "suggestion": "Keep this rhythm.",
            }
        if _contains_any(hint_blob, ["frown", "sad", "难过", "低落"]):
            return {
                "emotion": "sad",
                "intensity": 4,
                "cues": "downward mouth corners and low energy",
                "suggestion": "Offer gentle validation.",
            }
        if _contains_any(hint_blob, ["anx", "紧张", "焦虑", "stressed", "皱眉"]):
            return {
                "emotion": "anxious",
                "intensity": 4,
                "cues": "tense face and concentrated brow",
                "suggestion": "Guide a short breathing pause.",
            }
        if _contains_any(hint_blob, ["yawn", "sleepy", "疲惫", "困", "tired"]):
            return {
                "emotion": "tired",
                "intensity": 3,
                "cues": "fatigue-like expression",
                "suggestion": "Suggest a short rest.",
            }

        return {
            "emotion": "neutral",
            "intensity": 2,
            "cues": "no strong visual cues",
            "suggestion": "Continue normal companionship.",
        }

    async def evaluate_start_readiness(
        self,
        images: list[dict[str, Any]],
        current_task: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        _ = (current_task, session_id)
        has_camera = any(str(image.get("source", "")).lower() == "camera" for image in images)
        return {
            "approved": has_camera,
            "camera_ok": has_camera,
            "screen_ok": False,
            "reason": "camera ready" if has_camera else "camera image missing",
        }

    async def run_system_agent(
        self,
        session_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        _ = session_id
        user_text = str(inputs.get("user_text", "")).strip()
        lowered = user_text.lower()

        if _contains_any(
            user_text,
            [
                "看我",
                "看看我",
                "表情",
                "状态",
                "camera",
                "look at me",
                "how do i look",
            ],
        ):
            return {
                "action": "none",
                "approved": True,
                "mood_data": None,
                "requires_capture": True,
                "capture_sources": ["camera"],
                "system_events": ["[SYSTEM_RESULT: VISUAL_CONTEXT_REQUESTED, SOURCES: camera]"],
            }

        mood_requested = _contains_any(
            user_text,
            [
                "记录",
                "记一下",
                "心情",
                "情绪",
                "mood",
                "log",
                "feeling",
                "今天吃",
                "饮食",
                "meal",
                "ate",
            ],
        )

        if mood_requested:
            emotion, intensity = _infer_emotion_from_text(user_text)
            meal_info = ""
            if _contains_any(lowered, ["吃", "meal", "ate", "breakfast", "lunch", "dinner"]):
                meal_info = _truncate(user_text, 180)
            return {
                "action": "mood",
                "approved": True,
                "mood_data": {
                    "emotion": emotion,
                    "intensity": intensity,
                    "context": _truncate(user_text, 220),
                    "meal_info": meal_info,
                    "meal_emotion": emotion if meal_info else "",
                    "source": "chat",
                },
                "requires_capture": False,
                "capture_sources": [],
                "system_events": [],
            }

        if _contains_any(
            lowered,
            [
                "我叫",
                "我是",
                "我在",
                "我的专业",
                "my name",
                "i am",
                "i'm",
                "my major",
                "my school",
            ],
        ):
            return {
                "action": "profile",
                "approved": True,
                "mood_data": None,
                "requires_capture": False,
                "capture_sources": [],
                "system_events": ["[SYSTEM_RESULT: PROFILE_NOTED]"],
            }

        return {
            "action": "none",
            "approved": True,
            "mood_data": None,
            "requires_capture": False,
            "capture_sources": [],
            "system_events": [],
        }

    async def extract_profile_memories(
        self,
        session_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        _ = session_id
        rotated_chat = str(inputs.get("rotated_chat", ""))
        memory_lines: list[str] = []

        zh_name_match = re.search(r"我叫([^，。,.\n]{1,20})", rotated_chat)
        if zh_name_match:
            memory_lines.append(f"- 用户自称：{zh_name_match.group(1).strip()}")

        en_name_match = re.search(r"my name is\s+([A-Za-z][A-Za-z\s]{0,24})", rotated_chat, flags=re.IGNORECASE)
        if en_name_match:
            memory_lines.append(f"- User self-introduced as {en_name_match.group(1).strip()}")

        return {
            "should_update": bool(memory_lines),
            "memory_lines": memory_lines[:3],
        }
