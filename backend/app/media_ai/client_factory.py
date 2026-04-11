from __future__ import annotations

import os
from typing import Any

from .mock_agent_client import MockAgentClient


_client_instances: dict[str, Any] = {}


def get_agent_client() -> Any:
    """Return the configured agent client with singleton reuse.

    Values: "local" | "mock".
    """
    backend = os.getenv("AGENT_BACKEND", "local").strip().lower()
    if backend not in {"local", "mock"}:
        backend = "local"

    cached = _client_instances.get(backend)
    if cached is not None:
        return cached

    if backend == "local":
        from app.agent.local_client import LocalLLMClient

        client = LocalLLMClient()
    else:
        client = MockAgentClient()

    _client_instances[backend] = client
    return client
