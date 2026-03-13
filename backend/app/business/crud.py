import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
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

FEN_PER_RMB = Decimal("100")
SERVICE_FEE_PER_HOUR_RMB = Decimal("8.00")
PENALTY_PER_DISTRACTION = 300  # 单位：分，每走神一次扣3元
PROFILE_DOC_MAX_CHARS = 4000
CHAT_MESSAGE_MAX_CHARS = 2000


def _focus_fee_cents(planned_focus_minutes: int) -> int:
    """Calculate focus fee in cents from RMB 8/hour, rounded to 2 decimals RMB."""
    fee_rmb = (
        Decimal(planned_focus_minutes) * SERVICE_FEE_PER_HOUR_RMB / Decimal("60")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((fee_rmb * FEN_PER_RMB).to_integral_value(rounding=ROUND_HALF_UP))


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


def _require_wallet_for_update(db: Session, user_id: int) -> Wallet:
    wallet = (
        db.query(Wallet).with_for_update().filter(Wallet.user_id == user_id).first()
    )
    if not wallet:
        raise ValueError(f"wallet for user_id={user_id} not found")
    return wallet


def start_focus_session(db: Session, user_id: int, planned_focus_minutes: int) -> dict:
    if user_id in (0, 1):
        raise ValueError("user_id 0/1 are reserved system accounts")

    _get_or_create_user_with_wallet(db, user_id)

    # Always order locks by ID to avoid deadlocks
    # System IDs are 0 and 1, user IDs > 1
    pool_wallet = _require_wallet_for_update(db, 1)
    user_wallet = _require_wallet_for_update(db, user_id)

    upfront_cost = _focus_fee_cents(planned_focus_minutes)
    if user_wallet.balance < upfront_cost:
        raise ValueError(
            f"insufficient balance: need {upfront_cost}, have {user_wallet.balance}"
        )

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
                    "service_fee_per_hour_rmb": str(SERVICE_FEE_PER_HOUR_RMB),
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

    _get_or_create_user_with_wallet(db, user_id)

    # Always order locks by ID to avoid deadlocks
    # System IDs are 0 and 1, user IDs > 1
    charity_wallet = _require_wallet_for_update(db, 0)
    pool_wallet = _require_wallet_for_update(db, 1)
    user_wallet = _require_wallet_for_update(db, user_id)

    requested_penalty = (
        penalty_amount
        if penalty_amount is not None
        else distraction_count * PENALTY_PER_DISTRACTION
    )
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


def topup_wallet(
    db: Session, user_id: int, amount: int, reason: str = "User top-up"
) -> dict:
    if user_id in (0, 1):
        raise ValueError("cannot top-up system accounts directly")

    if amount <= 0:
        raise ValueError("top-up amount must be positive")

    _get_or_create_user_with_wallet(db, user_id)
    user_wallet = _require_wallet_for_update(db, user_id)

    tx_id = _new_tx_id()
    try:
        user_wallet.balance += amount
        db.add(
            Transaction(
                id=tx_id,
                tx_type="topup",
                to_user_id=user_id,
                amount=amount,
                reason=reason,
                meta_json=json.dumps(
                    {
                        "amount": amount,
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
        "amount": amount,
        "balance_after": user_wallet.balance,
        "tx_id": tx_id,
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

    def _parse_date_key(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None
        raw = raw.replace("/", "-")
        try:
            if len(raw) == 10:
                dt = datetime.strptime(raw, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _normalize_dates(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for item in value:
            date_key = _parse_date_key(item)
            if date_key:
                normalized.append(date_key)
        # Keep order but remove duplicates
        seen: set[str] = set()
        unique_dates: list[str] = []
        for item in normalized:
            if item in seen:
                continue
            seen.add(item)
            unique_dates.append(item)
        return unique_dates

    def _normalize_weekdays(value: object) -> list[int]:
        if not isinstance(value, list):
            return []
        normalized: list[int] = []
        for item in value:
            parsed = _parse_int(item)
            if parsed is None:
                continue
            if 0 <= parsed <= 6:
                normalized.append(parsed)
        return sorted(set(normalized))

    def _sanitize_text(value: object, max_len: int = 255) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return text[:max_len]

    normalized_plan_type = str(plan.get("planType") or "").strip().lower()
    if normalized_plan_type not in {"calendar", "task", "progress"}:
        normalized_plan_type = "calendar"

    normalized_start_date = _parse_date_key(plan.get("startDate"))
    normalized_end_date = _parse_date_key(plan.get("endDate"))
    normalized_deadline = _parse_date_key(
        plan.get("deadline") or plan.get("dueDate") or plan.get("endDate")
    )
    fallback_base = (
        datetime.strptime(normalized_start_date, "%Y-%m-%d")
        if normalized_start_date
        else datetime.utcnow()
    )

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
            normalized_minutes = (
                int(estimated_minutes) if estimated_minutes is not None else None
            )
        except (TypeError, ValueError):
            normalized_minutes = None
        actual_minutes = _parse_int(raw_task.get("actualMinutes"))
        if actual_minutes is not None and actual_minutes < 0:
            actual_minutes = 0

        task_date = _parse_date_key(raw_task.get("date") or raw_task.get("dueDate"))
        task_dates = _normalize_dates(raw_task.get("dates"))
        task_weekdays = _normalize_weekdays(raw_task.get("weekdays"))
        task_repeat_count = _parse_int(raw_task.get("repeatCount"))
        task_start_date = _parse_date_key(raw_task.get("startDate"))
        task_end_date = _parse_date_key(raw_task.get("endDate"))
        task_recurrence = str(raw_task.get("recurrence") or "").strip().lower()
        if task_recurrence not in {"daily", "weekly", "custom"}:
            task_recurrence = ""

        if (
            task_recurrence == "daily"
            and task_start_date
            and task_end_date
            and not task_dates
        ):
            try:
                start_dt = datetime.strptime(task_start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(task_end_date, "%Y-%m-%d")
                if end_dt >= start_dt:
                    span_days = min((end_dt - start_dt).days, 365)
                    task_dates = [
                        (start_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
                        for offset in range(span_days + 1)
                    ]
            except ValueError:
                pass

        # Fallback: if no explicit schedule is provided, place tasks on sequential days.
        if not task_date and not task_dates and not task_weekdays:
            fallback_date = (fallback_base + timedelta(days=index - 1)).strftime(
                "%Y-%m-%d"
            )
            task_date = fallback_date

        normalized_task: dict[str, Any] = {
            "id": str(raw_task.get("id") or f"task_{index}"),
            "title": title,
            "completed": bool(raw_task.get("completed", False)),
            "estimatedMinutes": normalized_minutes,
        }
        if actual_minutes is not None:
            normalized_task["actualMinutes"] = actual_minutes

        raw_actual_by_date = raw_task.get("actualMinutesByDate")
        if isinstance(raw_actual_by_date, dict):
            normalized_actual_by_date: dict[str, int] = {}
            for raw_date_key, raw_value in raw_actual_by_date.items():
                date_key = _parse_date_key(raw_date_key)
                parsed_minutes = _parse_int(raw_value)
                if date_key and parsed_minutes is not None and parsed_minutes >= 0:
                    normalized_actual_by_date[date_key] = parsed_minutes
            if normalized_actual_by_date:
                normalized_task["actualMinutesByDate"] = normalized_actual_by_date
        if task_date:
            normalized_task["date"] = task_date
        if task_dates:
            normalized_task["dates"] = task_dates
        if task_weekdays:
            normalized_task["weekdays"] = task_weekdays
        if task_repeat_count and task_repeat_count > 0:
            normalized_task["repeatCount"] = task_repeat_count
        if task_start_date:
            normalized_task["startDate"] = task_start_date
        if task_end_date:
            normalized_task["endDate"] = task_end_date
        if task_recurrence:
            normalized_task["recurrence"] = task_recurrence

        priority = str(raw_task.get("priority") or "").strip().lower()
        if priority in {"low", "medium", "high"}:
            normalized_task["priority"] = priority
        notes = _sanitize_text(raw_task.get("notes"), max_len=500)
        if notes:
            normalized_task["notes"] = notes

        tasks.append(normalized_task)

    total_minutes = plan.get("totalMinutes")
    normalized_total_minutes = _parse_int(total_minutes)
    if normalized_total_minutes is None:
        normalized_total_minutes = sum(
            task.get("estimatedMinutes") or 0 for task in tasks
        )

    suggested_duration = plan.get("suggestedDuration")
    derived_duration = 0
    first_task = tasks[0] if tasks else None
    first_task_minutes = (
        first_task.get("estimatedMinutes") if isinstance(first_task, dict) else None
    )
    if isinstance(first_task_minutes, int) and first_task_minutes > 0:
        derived_duration = first_task_minutes * 60
    elif normalized_total_minutes > 0 and len(tasks) <= 1:
        derived_duration = normalized_total_minutes * 60

    normalized_duration = _parse_int(suggested_duration)
    if normalized_duration is None:
        normalized_duration = derived_duration or max(normalized_total_minutes, 0) * 60

    if (
        derived_duration > 0
        and normalized_duration > 0
        and abs(normalized_duration - derived_duration) >= 60
    ):
        normalized_duration = derived_duration

    normalized_goal = _sanitize_text(plan.get("goal"), max_len=255)
    if not normalized_goal:
        normalized_goal = tasks[0].get("title") if tasks else "学习计划"

    result: dict[str, Any] = {
        "formatVersion": 2,
        "planType": normalized_plan_type,
        "goal": normalized_goal,
        "tasks": tasks,
        "totalMinutes": max(normalized_total_minutes, 0),
        "suggestedDuration": max(normalized_duration, 0),
    }
    if normalized_start_date:
        result["startDate"] = normalized_start_date
    if normalized_end_date:
        result["endDate"] = normalized_end_date
    if normalized_deadline:
        result["deadline"] = normalized_deadline
    return result


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

    try:
        raw_plan = json.loads(row.plan_json or "{}")
    except json.JSONDecodeError:
        raw_plan = {}
    normalized_plan = _normalize_plan(raw_plan if isinstance(raw_plan, dict) else {})
    if raw_plan != normalized_plan:
        row.plan_json = json.dumps(normalized_plan, ensure_ascii=False)
        row.title = str(
            (normalized_plan.get("tasks") or [{}])[0].get("title") or "学习计划"
        )
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)

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


def upsert_user_profile_document(
    db: Session, user_id: int, content: str
) -> dict[str, Any]:
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


def append_user_profile_memory(
    db: Session, user_id: int, memory_line: str
) -> dict[str, Any]:
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


def list_recent_chat_messages(
    db: Session, user_id: int, limit: int = 40
) -> dict[str, Any]:
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


def list_session_summaries(
    db: Session, user_id: int, limit: int = 20
) -> dict[str, Any]:
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


def list_user_transactions(
    db: Session, user_id: int, limit: int = 50
) -> dict[str, Any]:
    rows = (
        db.query(Transaction)
        .filter(
            (Transaction.from_user_id == user_id) | (Transaction.to_user_id == user_id)
        )
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
