from typing import List
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