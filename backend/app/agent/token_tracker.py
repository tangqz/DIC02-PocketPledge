import json
import logging
import os
from typing import Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Use an absolute path or relative to the backend directory
TOKEN_LOG_FILE = os.getenv("TOKEN_LOG_FILE", "token_usage.json")


def track_token_usage(
    model_name: str, usage: Any, session_id: str | None = None
) -> None:
    if not usage:
        return

    try:
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        total_tokens = getattr(usage, "total_tokens", 0)

        # Some providers return usage as a dict if we use chunk.usage
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": model_name,
            "session_id": session_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

        # Append to json list or lines
        with open(TOKEN_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    except Exception as e:
        logger.error(f"Failed to log token usage: {e}")
