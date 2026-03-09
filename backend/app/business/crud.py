import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from .models import Transaction, User, Wallet

SERVICE_FEE_PER_MINUTE = 15  # 单位：分，15分=0.15元/分钟
PENALTY_PER_DISTRACTION = 50  # 单位：分，每走神一次扣50分=0.5元


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _new_tx_id() -> str:
    return f"tx_{uuid.uuid4().hex[:24]}"


def _new_session_ref() -> str:
    return f"sess_{uuid.uuid4().hex[:16]}"


def _get_or_create_user_with_wallet(db: Session, user_id: int) -> tuple[User, Wallet]:
    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id, username=f"user_{user_id}", role="user")
        db.add(user)
        db.flush()

    wallet = db.get(Wallet, user_id)
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)
        db.flush()

    return user, wallet


def _require_wallet(db: Session, user_id: int) -> Wallet:
    wallet = db.get(Wallet, user_id)
    if not wallet:
        raise ValueError(f"wallet for user_id={user_id} not found")
    return wallet


def start_focus_session(db: Session, user_id: int, planned_focus_minutes: int) -> dict:
    if user_id in (0, 1):
        raise ValueError("user_id 0/1 are reserved system accounts")

    _, user_wallet = _get_or_create_user_with_wallet(db, user_id)
    pool_wallet = _require_wallet(db, 1)

    upfront_cost = planned_focus_minutes * SERVICE_FEE_PER_MINUTE
    if user_wallet.balance < upfront_cost:
        raise ValueError(f"insufficient balance: need {upfront_cost}, have {user_wallet.balance}")

    session_ref = _new_session_ref()
    tx_id = _new_tx_id()

    with db.begin():
        user_wallet.balance -= upfront_cost
        pool_wallet.balance += upfront_cost

        tx = Transaction(
            id=tx_id,
            tx_type="pre_paid_fee",
            from_user_id=user_id,
            to_user_id=1,
            amount=upfront_cost,
            reason=f"Pre-paid service fee for {planned_focus_minutes} min focus session",
            session_ref=session_ref,
            meta_json=json.dumps(
                {
                    "planned_focus_minutes": planned_focus_minutes,
                    "service_fee_per_minute": SERVICE_FEE_PER_MINUTE,
                    "created_at": _now_iso(),
                },
                ensure_ascii=False,
            ),
        )
        db.add(tx)

    db.refresh(user_wallet)
    db.refresh(pool_wallet)

    return {
        "ok": True,
        "user_id": user_id,
        "planned_focus_minutes": planned_focus_minutes,
        "upfront_cost": upfront_cost,
        "balance_after": user_wallet.balance,
        "pool_balance_after": pool_wallet.balance,
        "session_ref": session_ref,
        "tx_id": tx_id,
    }


def execute_penalty(
    db: Session,
    user_id: int,
    reason: str,
    distraction_count: int = 1,
    penalty_amount: int | None = None,
) -> dict:
    if user_id in (0, 1):
        raise ValueError("cannot execute penalty on system accounts")

    if distraction_count < 1:
        raise ValueError("distraction_count must be >= 1")

    _, user_wallet = _get_or_create_user_with_wallet(db, user_id)
    charity_wallet = _require_wallet(db, 0)
    pool_wallet = _require_wallet(db, 1)

    requested_penalty = penalty_amount if penalty_amount is not None else distraction_count * PENALTY_PER_DISTRACTION
    actual_penalty = min(requested_penalty, max(user_wallet.balance, 0))

    charity_amount = actual_penalty * 40 // 100
    pool_amount = actual_penalty - charity_amount

    charity_tx_id = _new_tx_id()
    pool_tx_id = _new_tx_id()

    with db.begin():
        user_wallet.balance -= actual_penalty
        charity_wallet.balance += charity_amount
        pool_wallet.balance += pool_amount

        if charity_amount > 0:
            db.add(
                Transaction(
                    id=charity_tx_id,
                    tx_type="penalty_to_charity",
                    from_user_id=user_id,
                    to_user_id=0,
                    amount=charity_amount,
                    reason=reason,
                    meta_json=json.dumps(
                        {
                            "distraction_count": distraction_count,
                            "penalty_per_distraction": PENALTY_PER_DISTRACTION,
                            "requested_penalty": requested_penalty,
                            "actual_penalty": actual_penalty,
                            "created_at": _now_iso(),
                        },
                        ensure_ascii=False,
                    ),
                )
            )

        if pool_amount > 0:
            db.add(
                Transaction(
                    id=pool_tx_id,
                    tx_type="penalty_to_pool",
                    from_user_id=user_id,
                    to_user_id=1,
                    amount=pool_amount,
                    reason=reason,
                    meta_json=json.dumps(
                        {
                            "distraction_count": distraction_count,
                            "penalty_per_distraction": PENALTY_PER_DISTRACTION,
                            "requested_penalty": requested_penalty,
                            "actual_penalty": actual_penalty,
                            "created_at": _now_iso(),
                        },
                        ensure_ascii=False,
                    ),
                )
            )

    db.refresh(user_wallet)

    return {
        "ok": True,
        "user_id": user_id,
        "distraction_count": distraction_count,
        "penalty_per_distraction": PENALTY_PER_DISTRACTION,
        "requested_penalty": requested_penalty,
        "actual_penalty": actual_penalty,
        "charity_amount": charity_amount,
        "pool_amount": pool_amount,
        "balance_after": user_wallet.balance,
        "is_bankrupt": user_wallet.balance <= 0,
        "tx_ids": [
            tx_id
            for tx_id in [
                charity_tx_id if charity_amount > 0 else None,
                pool_tx_id if pool_amount > 0 else None,
            ]
            if tx_id
        ],
    }


def get_user_status(db: Session, user_id: int) -> dict:
    if user_id in (0, 1):
        wallet = _require_wallet(db, user_id)
        return {
            "ok": True,
            "user_id": user_id,
            "balance": wallet.balance,
            "is_bankrupt": wallet.balance <= 0,
        }

    _get_or_create_user_with_wallet(db, user_id)
    wallet = _require_wallet(db, user_id)

    return {
        "ok": True,
        "user_id": user_id,
        "balance": wallet.balance,
        "is_bankrupt": wallet.balance <= 0,
    }