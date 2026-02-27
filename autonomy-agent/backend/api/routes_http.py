# api.py by kirura
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional

from backend.services.payment_service import (
    record_event_service,
    get_balance_service,
    get_history_service,
)

router = APIRouter(prefix="/api", tags=["reward"])

class BalanceChange(BaseModel):
    user_id: int = Field(..., ge=1)
    amount: int = Field(..., ge=1)
    type: Literal["reward", "penalty"]
    reason: str = Field(..., min_length=1, max_length=200)
    source: Literal["user", "supervisor", "agent"] = "user"
    evidence_id: Optional[str] = None

@router.get("/reward/balance/{user_id}")
def get_balance_api(user_id: int):
    return get_balance_service(user_id)

@router.get("/health")
def health():
    return {"ok": True}

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
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("error", "unknown error"))
    return result
# ed