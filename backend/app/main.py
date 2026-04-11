"""FastAPI application entrypoint for the backend service."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlencode
import asyncio

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.business.api import router as business_router
from app.business.models import init_db
from app.gateway.ws_router import router as gateway_router
from app.media_ai.asr_tts import warmup_asr_service


LOG_BODY_LIMIT = 1000


def _configure_logging() -> None:
    level_name = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    root_logger.setLevel(level)


def _truncate(value: str, limit: int = LOG_BODY_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, nested_value in value.items():
            if key.lower() in {
                "password",
                "token",
                "access_token",
                "refresh_token",
                "authorization",
                "api_key",
            }:
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive(nested_value)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


def _mask_query(query: str) -> str:
    if not query:
        return ""
    parsed = parse_qsl(query, keep_blank_values=True)
    masked_pairs = []
    for k, v in parsed:
        if k.lower() in {
            "password",
            "token",
            "access_token",
            "refresh_token",
            "authorization",
            "api_key",
        }:
            masked_pairs.append((k, "***"))
        else:
            masked_pairs.append((k, v))
    return urlencode(masked_pairs, safe="*")


def _format_body_for_log(body: bytes) -> str:
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _truncate(text)
    return _truncate(json.dumps(_mask_sensitive(parsed), ensure_ascii=False))


_configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Study Buddy Backend")

allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
allowed_origins = [
    origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    body = await request.body()
    body_preview = _format_body_for_log(body)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(request.scope, receive)
    logger.info(
        "http rx request_id=%s method=%s path=%s query=%s body=%s",
        request_id,
        request.method,
        request.url.path,
        _mask_query(request.url.query),
        body_preview,
    )

    started = time.perf_counter()
    response = await call_next(request)
    response_body = b""
    async for chunk in response.body_iterator:
        response_body += chunk
    elapsed_ms = (time.perf_counter() - started) * 1000
    response_preview = _format_body_for_log(response_body)
    logger.info(
        "http tx request_id=%s status=%s duration_ms=%.1f body=%s",
        request_id,
        response.status_code,
        elapsed_ms,
        response_preview,
    )
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )


@app.on_event("startup")
async def on_startup():
    init_db()
    warmup_timeout_seconds = max(
        1.0, float(os.getenv("MEDIA_AI_ASR_WARMUP_TIMEOUT", "30"))
    )
    try:
        await asyncio.wait_for(warmup_asr_service(), timeout=warmup_timeout_seconds)
    except TimeoutError:
        logger.warning(
            "ASR warmup timed out after %.1fs; backend continues startup",
            warmup_timeout_seconds,
        )
    except Exception:
        logger.exception("Unexpected ASR warmup failure; backend continues startup")
    logger.info(
        "backend startup complete agent_backend=%s asr_provider=%s",
        os.getenv("AGENT_BACKEND", "local"),
        os.getenv("MEDIA_AI_ASR_PROVIDER", "sherpa-onnx"),
    )


@app.get("/health")
def health():
    return {"ok": True, "service": "warmbuddy"}


app.include_router(auth_router)
app.include_router(business_router)
app.include_router(gateway_router)
