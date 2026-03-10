from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user_id
from .crud import execute_penalty, get_user_status, start_focus_session
from .models import get_db
from .schemas import (
    PenaltyExecuteRequest,
    PenaltyExecuteResponse,
    SessionStartRequest,
    SessionStartResponse,
    UserStatusResponse,
)

router = APIRouter(prefix="/api/business", tags=["business"])


@router.post("/session/start", response_model=SessionStartResponse)
def start_session_api(
    payload: SessionStartRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    try:
        return start_focus_session(
            db=db,
            user_id=current_user_id,
            planned_focus_minutes=payload.planned_focus_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/penalty/execute", response_model=PenaltyExecuteResponse)
def execute_penalty_api(
    payload: PenaltyExecuteRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    try:
        return execute_penalty(
            db=db,
            user_id=current_user_id,
            reason=payload.reason,
            distraction_count=payload.distraction_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me/status", response_model=UserStatusResponse)
def my_status_api(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    try:
        return get_user_status(db=db, user_id=current_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}/status", response_model=UserStatusResponse)
def user_status_api(user_id: int, db: Session = Depends(get_db)):
    """Internal/admin endpoint — kept for Dify tool callbacks."""
    try:
        return get_user_status(db=db, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))