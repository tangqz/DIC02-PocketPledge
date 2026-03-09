# backend/services/payment_service.py
# Reward + Escrow settlement logic (SQLite)

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any

from backend.models.database import get_conn

Source = Literal["user", "supervisor", "agent"]
PenaltyTarget = Literal["other_users", "charity"]

# A special internal account to represent "charity pool" (for MVP only)
CHARITY_USER_ID = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_user(conn, user_id: int) -> None:
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO users(user_id, balance_available, balance_locked) VALUES(?, 0, 0)",
            (user_id,),
        )


def _get_balances(conn, user_id: int) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute(
        "SELECT balance_available, balance_locked FROM users WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return 0, 0
    return int(row["balance_available"]), int(row["balance_locked"])


def _set_balances(conn, user_id: int, available: int, locked: int) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users(user_id, balance_available, balance_locked) VALUES(?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            balance_available=excluded.balance_available,
            balance_locked=excluded.balance_locked
        """,
        (user_id, available, locked),
    )


def _append_ledger(
    conn,
    *,
    user_id: int,
    kind: str,
    source: Source,
    amount: int,
    available_before: int,
    available_after: int,
    locked_before: int,
    locked_after: int,
    reason: str,
    session_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    counterparty_user_id: Optional[int] = None,
    target: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> str:
    event_id = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ledger(
            event_id, idempotency_key, user_id, session_id, kind, source, amount,
            available_before, available_after, locked_before, locked_after,
            reason, evidence_id, counterparty_user_id, target, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            idempotency_key,
            user_id,
            session_id,
            kind,
            source,
            amount,
            available_before,
            available_after,
            locked_before,
            locked_after,
            reason,
            evidence_id,
            counterparty_user_id,
            target,
            _utc_now(),
        ),
    )
    return event_id


# ---------- Public services (used by routes) ----------

def get_balance_service(user_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        ensure_user(conn, user_id)
        available, locked = _get_balances(conn, user_id)
        conn.commit()
        return {"ok": True, "user_id": user_id, "available": available, "locked": locked}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_history_service(user_id: int, limit: int = 20) -> Dict[str, Any]:
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        ensure_user(conn, user_id)
        limit = max(1, min(int(limit), 200))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM ledger
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
        return {"ok": True, "user_id": user_id, "count": len(rows), "items": rows}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_event_service(
    *,
    user_id: int,
    amount: int,
    event_type: Literal["reward", "penalty"],
    reason: str,
    source: Source = "user",
    evidence_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Simple balance change (no escrow). Use for top-up/reward/penalty MVP."""
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        ensure_user(conn, user_id)

        available_before, locked_before = _get_balances(conn, user_id)
        delta = amount if event_type == "reward" else -amount

        if available_before + delta < 0:
            conn.rollback()
            return {"ok": False, "error": "余额不足，不能扣到负数"}

        available_after = available_before + delta
        locked_after = locked_before
        _set_balances(conn, user_id, available_after, locked_after)

        kind = "reward" if event_type == "reward" else "penalty"
        event_id = _append_ledger(
            conn,
            user_id=user_id,
            kind=kind,
            source=source,
            amount=amount,
            available_before=available_before,
            available_after=available_after,
            locked_before=locked_before,
            locked_after=locked_after,
            reason=reason,
            evidence_id=evidence_id,
            idempotency_key=idempotency_key,
        )

        conn.commit()
        return {
            "ok": True,
            "event_id": event_id,
            "user_id": user_id,
            "available_before": available_before,
            "available_after": available_after,
            "locked_before": locked_before,
            "locked_after": locked_after,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_session_and_lock_deposit(
    *,
    session_id: str,
    user_id: int,
    duration_sec: int,
    category: str,
    deposit: int,
    penalty_target: PenaltyTarget,
    source: Source = "user",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a session record and move deposit from available -> locked."""
    if deposit <= 0:
        return {"ok": False, "error": "deposit must be > 0"}

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        ensure_user(conn, user_id)

        # Create session
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sessions(
                session_id, user_id, duration_sec, category, deposit, penalty_target,
                status, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'created', ?)
            """,
            (session_id, user_id, int(duration_sec), category, int(deposit), penalty_target, _utc_now()),
        )

        available_before, locked_before = _get_balances(conn, user_id)
        if available_before < deposit:
            conn.rollback()
            return {"ok": False, "error": "可用余额不足，无法锁定押金"}

        available_after = available_before - deposit
        locked_after = locked_before + deposit
        _set_balances(conn, user_id, available_after, locked_after)

        _append_ledger(
            conn,
            user_id=user_id,
            session_id=session_id,
            kind="lock",
            source=source,
            amount=deposit,
            available_before=available_before,
            available_after=available_after,
            locked_before=locked_before,
            locked_after=locked_after,
            reason=f"Lock deposit for session {session_id}",
            idempotency_key=idempotency_key,
        )

        conn.commit()
        return {
            "ok": True,
            "session_id": session_id,
            "user_id": user_id,
            "deposit": deposit,
            "available": available_after,
            "locked": locked_after,
        }
    except sqlite3.IntegrityError:  # type: ignore
        conn.rollback()
        return {"ok": False, "error": "session_id 已存在或幂等键重复"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def settle_session(
    *,
    session_id: str,
    score: int,
    source: Source = "agent",
    other_user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Settle: refund based on score, forfeit remainder to target."""
    score = max(0, min(int(score), 100))

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        cur = conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,))
        s = cur.fetchone()
        if not s:
            conn.rollback()
            return {"ok": False, "error": "session 不存在"}

        if s["status"] == "finished":
            conn.rollback()
            return {"ok": False, "error": "session 已结算"}

        user_id = int(s["user_id"])
        deposit = int(s["deposit"])
        penalty_target = str(s["penalty_target"])

        ensure_user(conn, user_id)
        if penalty_target == "charity":
            ensure_user(conn, CHARITY_USER_ID)

        # Compute amounts
        refund = int(round(deposit * score / 100))
        refund = max(0, min(refund, deposit))
        penalty = deposit - refund

        # Move locked -> available refund; locked -> (transfer)
        available_before, locked_before = _get_balances(conn, user_id)
        if locked_before < deposit:
            conn.rollback()
            return {"ok": False, "error": "锁定押金不足，无法结算（数据异常）"}

        # refund
        available_mid = available_before + refund
        locked_mid = locked_before - refund
        _set_balances(conn, user_id, available_mid, locked_mid)
        _append_ledger(
            conn,
            user_id=user_id,
            session_id=session_id,
            kind="refund",
            source=source,
            amount=refund,
            available_before=available_before,
            available_after=available_mid,
            locked_before=locked_before,
            locked_after=locked_mid,
            reason=f"Refund by score={score}",
            idempotency_key=idempotency_key,
        )

        # forfeit/transfer remaining
        if penalty > 0:
            available_before2, locked_before2 = _get_balances(conn, user_id)
            locked_after2 = locked_before2 - penalty
            _set_balances(conn, user_id, available_before2, locked_after2)
            _append_ledger(
                conn,
                user_id=user_id,
                session_id=session_id,
                kind="forfeit",
                source=source,
                amount=penalty,
                available_before=available_before2,
                available_after=available_before2,
                locked_before=locked_before2,
                locked_after=locked_after2,
                reason=f"Forfeit by score={score}",
            )

            # transfer destination
            if penalty_target == "charity":
                to_user = CHARITY_USER_ID
                target = "charity"
            else:
                # other_users
                if other_user_id is None or other_user_id < 1:
                    conn.rollback()
                    return {"ok": False, "error": "penalty_target=other_users 需要 other_user_id"}
                to_user = int(other_user_id)
                target = "other_users"
                ensure_user(conn, to_user)

            to_av_before, to_locked_before = _get_balances(conn, to_user)
            to_av_after = to_av_before + penalty
            _set_balances(conn, to_user, to_av_after, to_locked_before)
            _append_ledger(
                conn,
                user_id=to_user,
                session_id=session_id,
                kind="transfer_in",
                source=source,
                amount=penalty,
                available_before=to_av_before,
                available_after=to_av_after,
                locked_before=to_locked_before,
                locked_after=to_locked_before,
                reason=f"Penalty received from user {user_id}",
                counterparty_user_id=user_id,
                target=target,
            )

        # mark finished
        cur.execute(
            """
            UPDATE sessions SET
                status='finished',
                score=?,
                refund_amount=?,
                penalty_amount=?,
                finished_at=?
            WHERE session_id=?
            """,
            (score, refund, penalty, _utc_now(), session_id),
        )

        conn.commit()
        return {
            "ok": True,
            "session_id": session_id,
            "user_id": user_id,
            "deposit": deposit,
            "score": score,
            "refund": refund,
            "penalty": penalty,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
