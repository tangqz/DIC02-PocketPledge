# backend/api/routes_http.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
import time, json

from backend.models.database import get_conn

from backend.services.payment_service import (
    record_event_service,
    get_balance_service,
    get_history_service,
    create_session_and_lock_deposit,
    settle_session,
)

router = APIRouter(prefix="/api", tags=["reward"])


class BalanceChange(BaseModel):
    user_id: int = Field(..., ge=0)
    amount: int = Field(..., ge=1)
    type: Literal["reward", "penalty"]
    reason: str = Field(..., min_length=1, max_length=200)
    source: Literal["user", "supervisor", "agent"] = "user"
    evidence_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(
        default=None,
        description="可选：用于防止重复记账（比如前端重试）。同一 key 只能成功一次。",
    )


class SessionLockIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    user_id: int = Field(..., ge=1)
    duration_sec: int = Field(..., ge=60, le=8 * 60 * 60)
    category: str = Field(..., min_length=1, max_length=50)
    deposit: int = Field(..., ge=1)
    penalty_target: Literal["other_users", "charity"]
    source: Literal["user", "supervisor", "agent"] = "user"
    idempotency_key: Optional[str] = None


class SessionSettleIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    score: int = Field(..., ge=0, le=100)
    other_user_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="当 penalty_target=other_users 时需要",
    )
    source: Literal["user", "supervisor", "agent"] = "agent"
    idempotency_key: Optional[str] = None

# ---- session events (evidence / telemetry) ----
EventType = Literal["heartbeat", "screen", "webcam", "audio", "manual_note"]

class SessionEventIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    user_id: int = Field(..., ge=1)
    event_type: EventType
    payload: Dict[str, Any] = Field(default_factory=dict)
    ts: Optional[int] = Field(default=None, description="可选：unix时间戳（秒）。不传则用服务器当前时间")

@router.get("/health")
def health():
    return {"ok": True}


@router.get("/reward/balance/{user_id}")
def get_balance_api(user_id: int):
    return get_balance_service(user_id)


@router.get("/reward/history/{user_id}")
def get_history_api(user_id: int, limit: int = 20):
    return get_history_service(user_id, limit)


@router.post("/reward/event")
def record_event_api(payload: BalanceChange):
    result = record_event_service(
        user_id=payload.user_id,
        amount=payload.amount,
        event_type=payload.type,
        reason=payload.reason,
        source=payload.source,
        evidence_id=payload.evidence_id,
        idempotency_key=payload.idempotency_key,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "unknown error"))
    return result


@router.post("/escrow/lock")
def lock_deposit_api(payload: SessionLockIn):
    result = create_session_and_lock_deposit(
        session_id=payload.session_id,
        user_id=payload.user_id,
        duration_sec=payload.duration_sec,
        category=payload.category,
        deposit=payload.deposit,
        penalty_target=payload.penalty_target,
        source=payload.source,
        idempotency_key=payload.idempotency_key,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "unknown error"))
    return result


@router.post("/escrow/settle")
def settle_api(payload: SessionSettleIn):
    result = settle_session(
        session_id=payload.session_id,
        score=payload.score,
        other_user_id=payload.other_user_id,
        source=payload.source,
        idempotency_key=payload.idempotency_key,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "unknown error"))
    return result

@router.post("/sessions/event")
def post_session_event(payload: SessionEventIn):
    ts = payload.ts or int(time.time())
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO session_events(session_id, user_id, ts, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
            (
                payload.session_id,
                payload.user_id,
                ts,
                payload.event_type,
                json.dumps(payload.payload, ensure_ascii=False),
            ),
        )
        conn.commit()
        return {"ok": True, "ts": ts}
    finally:
        conn.close()


@router.get("/sessions/events/{session_id}")
def list_session_events(session_id: str, limit: int = 100):
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, session_id, user_id, ts, event_type, payload_json FROM session_events WHERE session_id=? ORDER BY ts ASC LIMIT ?",
            (session_id, limit),
        )
        rows = cur.fetchall()
        return {
            "ok": True,
            "session_id": session_id,
            "events": [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "ts": r["ts"],
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload_json"]),
                }
                for r in rows
            ],
        }
    finally:
        conn.close()