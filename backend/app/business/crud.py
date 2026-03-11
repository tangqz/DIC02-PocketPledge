import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import (
    ChatMessage,
    PauseRequest,
    SessionSummary,
    StudyPlan,
    Transaction,
    User,
    UserProfileDocument,
    Wallet,
)

SERVICE_FEE_PER_MINUTE = 15  # 单位：分，15分=0.15元/分钟
PENALTY_PER_DISTRACTION = 50  # 单位：分，每走神一次扣50分=0.5元
PROFILE_DOC_MAX_CHARS = 4000
CHAT_MESSAGE_MAX_CHARS = 2000


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

    try:
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
        db.commit()
    except Exception:
        db.rollback()
        raise

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

    try:
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
        db.commit()
    except Exception:
        db.rollback()
        raise

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


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    def _parse_int(value: object) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(stripped)
            except ValueError:
                return None
        return None

    raw_tasks = plan.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    for index, raw_task in enumerate(raw_tasks, start=1):
        if not isinstance(raw_task, dict):
            continue
        title = str(raw_task.get("title") or "").strip()
        if not title:
            continue
        estimated_minutes = raw_task.get("estimatedMinutes")
        try:
            normalized_minutes = int(estimated_minutes) if estimated_minutes is not None else None
        except (TypeError, ValueError):
            normalized_minutes = None
        tasks.append(
            {
                "id": str(raw_task.get("id") or f"task_{index}"),
                "title": title,
                "completed": bool(raw_task.get("completed", False)),
                "estimatedMinutes": normalized_minutes,
            }
        )

    total_minutes = plan.get("totalMinutes")
    normalized_total_minutes = _parse_int(total_minutes)
    if normalized_total_minutes is None:
        normalized_total_minutes = sum(task.get("estimatedMinutes") or 0 for task in tasks)

    suggested_duration = plan.get("suggestedDuration")
    derived_duration = 0
    first_task = tasks[0] if tasks else None
    first_task_minutes = first_task.get("estimatedMinutes") if isinstance(first_task, dict) else None
    if isinstance(first_task_minutes, int) and first_task_minutes > 0:
        derived_duration = first_task_minutes * 60
    elif normalized_total_minutes > 0 and len(tasks) <= 1:
        derived_duration = normalized_total_minutes * 60

    normalized_duration = _parse_int(suggested_duration)
    if normalized_duration is None:
        normalized_duration = derived_duration or max(normalized_total_minutes, 0) * 60

    if derived_duration > 0 and normalized_duration > 0 and abs(normalized_duration - derived_duration) >= 60:
        normalized_duration = derived_duration

    return {
        "tasks": tasks,
        "totalMinutes": max(normalized_total_minutes, 0),
        "suggestedDuration": max(normalized_duration, 0),
    }


def _serialize_plan_row(row: StudyPlan) -> dict[str, Any]:
    plan = json.loads(row.plan_json or "{}")
    return {
        "ok": True,
        "plan_id": row.id,
        "title": row.title,
        "status": row.status,
        "source": row.source,
        "plan": plan,
        "updated_at": row.updated_at.isoformat(),
    }


def get_active_plan(db: Session, user_id: int) -> dict[str, Any] | None:
    row = (
        db.query(StudyPlan)
        .filter(StudyPlan.user_id == user_id, StudyPlan.status == "active")
        .order_by(StudyPlan.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    return _serialize_plan_row(row)


def upsert_study_plan(
    db: Session,
    user_id: int,
    plan: dict[str, Any],
    source: str = "system_agent",
) -> dict[str, Any]:
    normalized_plan = _normalize_plan(plan)
    tasks = normalized_plan.get("tasks") or []
    title = str(tasks[0].get("title") if tasks else "学习计划")
    now = datetime.utcnow()

    row = (
        db.query(StudyPlan)
        .filter(StudyPlan.user_id == user_id, StudyPlan.status == "active")
        .order_by(StudyPlan.updated_at.desc())
        .first()
    )
    if row is None:
        row = StudyPlan(
            id=f"plan_{uuid.uuid4().hex[:24]}",
            user_id=user_id,
            title=title,
            status="active",
            plan_json=json.dumps(normalized_plan, ensure_ascii=False),
            source=source,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.title = title
        row.plan_json = json.dumps(normalized_plan, ensure_ascii=False)
        row.source = source
        row.updated_at = now

    db.commit()
    db.refresh(row)
    return _serialize_plan_row(row)


def get_user_profile_document(db: Session, user_id: int) -> dict[str, Any]:
    row = db.get(UserProfileDocument, user_id)
    return {
        "ok": True,
        "user_id": user_id,
        "content": row.content if row else "",
        "updated_at": row.updated_at.isoformat() if row else None,
        "max_chars": PROFILE_DOC_MAX_CHARS,
    }


def upsert_user_profile_document(db: Session, user_id: int, content: str) -> dict[str, Any]:
    normalized_content = content.strip()
    if len(normalized_content) > PROFILE_DOC_MAX_CHARS:
        normalized_content = normalized_content[:PROFILE_DOC_MAX_CHARS]

    row = db.get(UserProfileDocument, user_id)
    now = datetime.utcnow()
    if row is None:
        row = UserProfileDocument(
            user_id=user_id,
            content=normalized_content,
            updated_at=now,
        )
        db.add(row)
    else:
        row.content = normalized_content
        row.updated_at = now

    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "user_id": user_id,
        "content": row.content,
        "updated_at": row.updated_at.isoformat(),
        "max_chars": PROFILE_DOC_MAX_CHARS,
    }


def append_user_profile_memory(db: Session, user_id: int, memory_line: str) -> dict[str, Any]:
    """Append one profile memory line while keeping the profile document bounded."""
    normalized_line = memory_line.strip()
    if not normalized_line:
        return get_user_profile_document(db, user_id)

    current = get_user_profile_document(db, user_id).get("content", "")
    merged = f"{current}\n{normalized_line}".strip() if current else normalized_line

    # Keep recent lines to respect max size.
    lines = [line.strip() for line in merged.splitlines() if line.strip()]
    while lines and len("\n".join(lines)) > PROFILE_DOC_MAX_CHARS:
        lines.pop(0)

    return upsert_user_profile_document(db, user_id, "\n".join(lines))


def create_chat_message(
    db: Session,
    user_id: int,
    role: str,
    content: str,
    session_ref: str | None = None,
) -> dict[str, Any]:
    normalized_role = role.strip().lower()
    if normalized_role not in {"user", "assistant", "system"}:
        normalized_role = "system"

    normalized_content = content.strip()
    if not normalized_content:
        return {"ok": False, "error": "empty content"}
    if len(normalized_content) > CHAT_MESSAGE_MAX_CHARS:
        normalized_content = normalized_content[:CHAT_MESSAGE_MAX_CHARS]

    row = ChatMessage(
        id=f"chat_{uuid.uuid4().hex[:24]}",
        user_id=user_id,
        session_ref=session_ref,
        role=normalized_role,
        content=normalized_content,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "id": row.id,
        "user_id": row.user_id,
        "session_ref": row.session_ref,
        "role": row.role,
        "content": row.content,
        "created_at": row.created_at.isoformat(),
    }


def list_recent_chat_messages(db: Session, user_id: int, limit: int = 40) -> dict[str, Any]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    ordered_rows = list(reversed(rows))
    items = [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "session_ref": row.session_ref,
            "created_at": row.created_at.isoformat(),
        }
        for row in ordered_rows
    ]
    return {
        "ok": True,
        "user_id": user_id,
        "items": items,
    }


def _serialize_pause_request(row: PauseRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_ref": row.session_ref,
        "requested_text": row.requested_text,
        "approved": row.approved,
        "pause_seconds": row.pause_seconds,
        "decision_reason": row.decision_reason,
        "created_at": row.created_at.isoformat(),
    }


def record_pause_request(
    db: Session,
    user_id: int,
    requested_text: str,
    approved: bool,
    pause_seconds: int | None = None,
    decision_reason: str = "",
    session_ref: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = PauseRequest(
        id=f"pause_{uuid.uuid4().hex[:24]}",
        user_id=user_id,
        session_ref=session_ref,
        requested_text=requested_text.strip(),
        approved=approved,
        pause_seconds=pause_seconds,
        decision_reason=decision_reason.strip(),
        meta_json=json.dumps(meta or {}, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    payload = _serialize_pause_request(row)
    payload["ok"] = True
    return payload


def list_pause_requests(db: Session, user_id: int, limit: int = 20) -> dict[str, Any]:
    rows = (
        db.query(PauseRequest)
        .filter(PauseRequest.user_id == user_id)
        .order_by(PauseRequest.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return {
        "ok": True,
        "user_id": user_id,
        "items": [_serialize_pause_request(row) for row in rows],
    }


def _serialize_session_summary(row: SessionSummary) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_ref": row.session_ref,
        "summary_text": row.summary_text,
        "created_at": row.created_at.isoformat(),
    }


def create_session_summary(
    db: Session,
    user_id: int,
    summary_text: str,
    session_ref: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = SessionSummary(
        id=f"summary_{uuid.uuid4().hex[:24]}",
        user_id=user_id,
        session_ref=session_ref,
        summary_text=summary_text.strip(),
        meta_json=json.dumps(meta or {}, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    payload = _serialize_session_summary(row)
    payload["ok"] = True
    return payload


def list_session_summaries(db: Session, user_id: int, limit: int = 20) -> dict[str, Any]:
    rows = (
        db.query(SessionSummary)
        .filter(SessionSummary.user_id == user_id)
        .order_by(SessionSummary.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return {
        "ok": True,
        "user_id": user_id,
        "items": [_serialize_session_summary(row) for row in rows],
    }


def list_user_transactions(db: Session, user_id: int, limit: int = 50) -> dict[str, Any]:
    rows = (
        db.query(Transaction)
        .filter((Transaction.from_user_id == user_id) | (Transaction.to_user_id == user_id))
        .order_by(Transaction.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    items = []
    for row in rows:
        try:
            meta = json.loads(row.meta_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        items.append(
            {
                "id": row.id,
                "tx_type": row.tx_type,
                "from_user_id": row.from_user_id,
                "to_user_id": row.to_user_id,
                "amount": row.amount,
                "reason": row.reason,
                "session_ref": row.session_ref,
                "created_at": row.created_at.isoformat(),
                "meta": meta,
            }
        )
    return {
        "ok": True,
        "user_id": user_id,
        "items": items,
    }