"""Tool definitions and executor for the local system agent."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.business.models import SessionLocal
from app.business.crud import (
    get_active_plan,
    get_user_profile_document,
    get_user_status,
    list_pause_requests,
    list_session_summaries,
    list_user_transactions,
    upsert_study_plan,
    upsert_user_profile_document,
)

logger = logging.getLogger(__name__)


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_user_status",
            "description": "查询当前用户的余额和破产状态",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_plan",
            "description": "获取当前用户活跃的学习计划",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_plan",
            "description": "创建或更新当前用户的学习计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "description": "任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "completed": {"type": "boolean"},
                                "estimatedMinutes": {"type": "integer"},
                            },
                            "required": ["id", "title"],
                        },
                    },
                    "totalMinutes": {"type": "integer", "description": "总分钟数"},
                    "suggestedDuration": {
                        "type": "integer",
                        "description": "建议专注时长（秒）",
                    },
                },
                "required": ["tasks", "totalMinutes", "suggestedDuration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "获取当前用户的画像文档",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "更新当前用户的画像文档内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "新的画像文档内容（纯文本）",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pause_requests",
            "description": "查询当前用户的历史暂停申请记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_session_summaries",
            "description": "查询当前用户的历史会话总结",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_user_transactions",
            "description": "查询当前用户的交易/扣费记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
]


def execute_tool(tool_name: str, arguments: dict[str, Any], user_id: int) -> str:
    """Execute a system agent tool call synchronously and return JSON result."""
    db = SessionLocal()
    try:
        result = _dispatch(tool_name, arguments, user_id, db)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.exception("tool execution failed: %s", tool_name)
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    finally:
        db.close()


def _dispatch(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: int,
    db: Any,
) -> Any:
    if tool_name == "get_user_status":
        return get_user_status(db, user_id)

    if tool_name == "get_user_plan":
        result = get_active_plan(db, user_id)
        return result or {"ok": True, "plan": None, "message": "当前没有活跃的学习计划"}

    if tool_name == "update_user_plan":
        return upsert_study_plan(db, user_id, plan=arguments, source="system_agent")

    if tool_name == "get_user_profile":
        return get_user_profile_document(db, user_id)

    if tool_name == "update_user_profile":
        return upsert_user_profile_document(
            db, user_id, content=arguments.get("content", "")
        )

    if tool_name == "list_pause_requests":
        return list_pause_requests(db, user_id, limit=arguments.get("limit", 10))

    if tool_name == "list_session_summaries":
        return list_session_summaries(db, user_id, limit=arguments.get("limit", 10))

    if tool_name == "list_user_transactions":
        return list_user_transactions(db, user_id, limit=arguments.get("limit", 20))

    return {"error": f"unknown tool: {tool_name}"}
