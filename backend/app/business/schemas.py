from typing import Any, List
from pydantic import BaseModel, Field


class SessionStartRequest(BaseModel):
    planned_focus_minutes: int = Field(..., ge=1, le=600)


class SessionStartResponse(BaseModel):
    ok: bool
    user_id: int
    planned_focus_minutes: int
    upfront_cost: int
    balance_after: int
    pool_balance_after: int
    session_ref: str
    tx_id: str


class PenaltyExecuteRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)
    distraction_count: int = Field(default=1, ge=1)


class PenaltyExecuteResponse(BaseModel):
    ok: bool
    user_id: int
    distraction_count: int
    penalty_per_distraction: int
    requested_penalty: int
    actual_penalty: int
    charity_amount: int
    pool_amount: int
    balance_after: int
    is_bankrupt: bool
    tx_ids: List[str]


class UserStatusResponse(BaseModel):
    ok: bool
    user_id: int
    balance: int
    is_bankrupt: bool


class PlanTaskPayload(BaseModel):
    id: str
    title: str = Field(..., min_length=1, max_length=255)
    completed: bool = False
    estimatedMinutes: int | None = Field(default=None, ge=1, le=1440)


class PlanPayload(BaseModel):
    tasks: List[PlanTaskPayload]
    totalMinutes: int = Field(..., ge=0, le=10080)
    suggestedDuration: int | None = Field(default=None, ge=0, le=604800)


class PlanDocumentResponse(BaseModel):
    ok: bool
    plan_id: str | None = None
    title: str | None = None
    status: str | None = None
    source: str | None = None
    plan: PlanPayload | None = None
    updated_at: str | None = None


class ProfileDocumentRequest(BaseModel):
    content: str = Field(..., min_length=0, max_length=4000)


class ProfileDocumentResponse(BaseModel):
    ok: bool
    user_id: int
    content: str
    updated_at: str | None = None
    max_chars: int


class PauseRequestCreate(BaseModel):
    requested_text: str = Field(..., min_length=1, max_length=2000)
    approved: bool
    pause_seconds: int | None = Field(default=None, ge=0, le=3600)
    decision_reason: str = Field(default="", max_length=255)
    session_ref: str | None = Field(default=None, max_length=100)
    meta: dict[str, Any] | None = None


class PauseRequestItem(BaseModel):
    id: str
    session_ref: str | None = None
    requested_text: str
    approved: bool
    pause_seconds: int | None = None
    decision_reason: str
    created_at: str


class PauseRequestListResponse(BaseModel):
    ok: bool
    user_id: int
    items: List[PauseRequestItem]


class SessionSummaryCreate(BaseModel):
    summary_text: str = Field(..., min_length=1, max_length=4000)
    session_ref: str | None = Field(default=None, max_length=100)
    meta: dict[str, Any] | None = None


class SessionSummaryItem(BaseModel):
    id: str
    session_ref: str | None = None
    summary_text: str
    created_at: str


class SessionSummaryListResponse(BaseModel):
    ok: bool
    user_id: int
    items: List[SessionSummaryItem]


class TransactionItem(BaseModel):
    id: str
    tx_type: str
    from_user_id: int | None = None
    to_user_id: int | None = None
    amount: int
    reason: str
    session_ref: str | None = None
    created_at: str
    meta: dict[str, Any] = {}


class TransactionListResponse(BaseModel):
    ok: bool
    user_id: int
    items: List[TransactionItem]