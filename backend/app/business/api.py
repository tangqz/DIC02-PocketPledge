import os
import hmac

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user_id
from .crud import (
    create_session_summary,
    execute_penalty,
    get_active_plan,
    get_user_profile_document,
    get_user_status,
    list_pause_requests,
    list_session_summaries,
    list_user_transactions,
    record_pause_request,
    start_focus_session,
    upsert_study_plan,
    upsert_user_profile_document,
)
from .models import get_db
from .schemas import (
    PauseRequestCreate,
    PauseRequestListResponse,
    PenaltyExecuteRequest,
    PenaltyExecuteResponse,
    PlanDocumentResponse,
    PlanPayload,
    ProfileDocumentRequest,
    ProfileDocumentResponse,
    SessionStartRequest,
    SessionStartResponse,
    SessionSummaryCreate,
    SessionSummaryListResponse,
    TransactionListResponse,
    UserStatusResponse,
)

router = APIRouter(prefix="/api/business", tags=["business"])
_internal_bearer = HTTPBearer(auto_error=False)


def require_internal_tool_access(
    creds: HTTPAuthorizationCredentials | None = Depends(_internal_bearer),
) -> None:
    configured_token = os.getenv("DIFY_TOOL_BEARER_TOKEN", "").strip()
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal tool token is not configured",
        )

    if creds is None or not hmac.compare_digest(
        creds.credentials.encode("utf-8"), configured_token.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal tool token",
        )


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
def user_status_api(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    """Internal endpoint secured for Dify tool callbacks."""
    try:
        return get_user_status(db=db, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/internal/users/{user_id}/plan", response_model=PlanDocumentResponse)
def internal_user_plan_api(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    plan = get_active_plan(db=db, user_id=user_id)
    if plan is None:
        return PlanDocumentResponse(ok=True)
    return plan


@router.put("/internal/users/{user_id}/plan", response_model=PlanDocumentResponse)
def internal_update_user_plan_api(
    user_id: int,
    payload: PlanPayload,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    return upsert_study_plan(
        db=db,
        user_id=user_id,
        plan=payload.model_dump(),
        source="dify_tool",
    )


@router.get("/internal/users/{user_id}/profile", response_model=ProfileDocumentResponse)
def internal_user_profile_api(
    user_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    return get_user_profile_document(db=db, user_id=user_id)


@router.put("/internal/users/{user_id}/profile", response_model=ProfileDocumentResponse)
def internal_update_user_profile_api(
    user_id: int,
    payload: ProfileDocumentRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    return upsert_user_profile_document(
        db=db,
        user_id=user_id,
        content=payload.content,
    )


@router.get(
    "/internal/users/{user_id}/pause-requests", response_model=PauseRequestListResponse
)
def internal_pause_requests_api(
    user_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    return list_pause_requests(db=db, user_id=user_id, limit=limit)


@router.post(
    "/internal/users/{user_id}/pause-requests", response_model=PauseRequestListResponse
)
def internal_create_pause_request_api(
    user_id: int,
    payload: PauseRequestCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    record_pause_request(
        db=db,
        user_id=user_id,
        requested_text=payload.requested_text,
        approved=payload.approved,
        pause_seconds=payload.pause_seconds,
        decision_reason=payload.decision_reason,
        session_ref=payload.session_ref,
        meta=payload.meta,
    )
    return list_pause_requests(db=db, user_id=user_id, limit=20)


@router.get(
    "/internal/users/{user_id}/session-summaries",
    response_model=SessionSummaryListResponse,
)
def internal_session_summaries_api(
    user_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    return list_session_summaries(db=db, user_id=user_id, limit=limit)


@router.post(
    "/internal/users/{user_id}/session-summaries",
    response_model=SessionSummaryListResponse,
)
def internal_create_session_summary_api(
    user_id: int,
    payload: SessionSummaryCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    create_session_summary(
        db=db,
        user_id=user_id,
        summary_text=payload.summary_text,
        session_ref=payload.session_ref,
        meta=payload.meta,
    )
    return list_session_summaries(db=db, user_id=user_id, limit=20)


@router.get(
    "/internal/users/{user_id}/transactions", response_model=TransactionListResponse
)
def internal_transactions_api(
    user_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_tool_access),
):
    return list_user_transactions(db=db, user_id=user_id, limit=limit)


@router.get("/me/plan", response_model=PlanDocumentResponse)
def my_plan_api(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    plan = get_active_plan(db=db, user_id=current_user_id)
    if plan is None:
        return PlanDocumentResponse(ok=True)
    return plan


@router.put("/me/plan", response_model=PlanDocumentResponse)
def update_my_plan_api(
    payload: PlanPayload,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    return upsert_study_plan(
        db=db,
        user_id=current_user_id,
        plan=payload.model_dump(),
        source="api",
    )


@router.get("/me/profile", response_model=ProfileDocumentResponse)
def my_profile_api(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    return get_user_profile_document(db=db, user_id=current_user_id)


@router.put("/me/profile", response_model=ProfileDocumentResponse)
def update_my_profile_api(
    payload: ProfileDocumentRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    return upsert_user_profile_document(
        db=db,
        user_id=current_user_id,
        content=payload.content,
    )


@router.get("/me/pause-requests", response_model=PauseRequestListResponse)
def my_pause_requests_api(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    return list_pause_requests(db=db, user_id=current_user_id, limit=limit)


@router.post("/me/pause-requests", response_model=PauseRequestListResponse)
def create_pause_request_api(
    payload: PauseRequestCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    record_pause_request(
        db=db,
        user_id=current_user_id,
        requested_text=payload.requested_text,
        approved=payload.approved,
        pause_seconds=payload.pause_seconds,
        decision_reason=payload.decision_reason,
        session_ref=payload.session_ref,
        meta=payload.meta,
    )
    return list_pause_requests(db=db, user_id=current_user_id, limit=20)


@router.get("/me/session-summaries", response_model=SessionSummaryListResponse)
def my_session_summaries_api(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    return list_session_summaries(db=db, user_id=current_user_id, limit=limit)


@router.post("/me/session-summaries", response_model=SessionSummaryListResponse)
def create_session_summary_api(
    payload: SessionSummaryCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    create_session_summary(
        db=db,
        user_id=current_user_id,
        summary_text=payload.summary_text,
        session_ref=payload.session_ref,
        meta=payload.meta,
    )
    return list_session_summaries(db=db, user_id=current_user_id, limit=20)


@router.get("/me/transactions", response_model=TransactionListResponse)
def my_transactions_api(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    return list_user_transactions(db=db, user_id=current_user_id, limit=limit)
