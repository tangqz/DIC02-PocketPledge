from __future__ import annotations

import os
from typing import Any

from .dify_proxy import DifyClient, MockDifyClient


_client_instances: dict[str, Any] = {}


def get_agent_client() -> Any:
    """Return the configured agent client with singleton reuse.

    Values: "local" | "dify" | "mock" (default).
    Legacy MEDIA_AI_USE_REAL_DIFY=1 is still respected as a fallback.
    """
    backend = os.getenv("AGENT_BACKEND", "").strip().lower()
    if backend not in {"local", "dify", "mock"}:
        backend = "dify" if os.getenv("MEDIA_AI_USE_REAL_DIFY", "0") == "1" else "mock"

    cached = _client_instances.get(backend)
    if cached is not None:
        return cached

    if backend == "local":
        from app.agent.local_client import LocalLLMClient

        client = LocalLLMClient()
    elif backend == "dify":
        client = DifyClient()
    else:
        client = MockDifyClient()

    _client_instances[backend] = client
    return client
