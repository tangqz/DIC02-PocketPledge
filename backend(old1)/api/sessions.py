from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
import uuid

from backend.services.payment_service import (
    create_session_and_lock_deposit as lock_deposit,
    settle_session,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class StartReq(BaseModel):
    user_id: int
    duration_sec: int = Field(ge=60)
    category: str
    deposit: int = Field(ge=1)
    penalty_target: Literal["charity", "other_users"]
    # 先保留字段，但 lock 阶段不会传给 payment_service
    other_user_id: Optional[int] = None


class FinishReq(BaseModel):
    session_id: str
    score: int = Field(ge=0, le=100)
    # finish 阶段也先保留
    other_user_id: Optional[int] = None


@router.post("/start")
def start(req: StartReq):
    session_id = f"sess_{uuid.uuid4().hex[:8]}"

    try:
        lock_result = lock_deposit(
            session_id=session_id,
            user_id=req.user_id,
            duration_sec=req.duration_sec,
            category=req.category,
            deposit=req.deposit,
            penalty_target=req.penalty_target,
            source="user",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    plan = [
        {"work_min": 25, "rest_min": 5},
        {"work_min": 25, "rest_min": 5},
    ]

    return {
        "ok": True,
        "session_id": session_id,
        "start_at": datetime.utcnow().isoformat(),
        "plan": plan,
        "lock": lock_result,
    }


@router.post("/finish")
def finish(req: FinishReq):
    try:
        settle_result = settle_session(
            session_id=req.session_id,
            score=req.score,
            # settle_session 不支持 other_user_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"ok": True, "settle": settle_result}