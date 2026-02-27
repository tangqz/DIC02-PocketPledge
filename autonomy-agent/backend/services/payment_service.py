# payment_service.py by kirura
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal, Dict, Any

from backend.models.database import get_conn

def ensure_user(conn, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users(user_id, balance) VALUES(?, 0)", (user_id,))
        conn.commit()

def get_balance_db(conn, user_id: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return int(row["balance"]) if row else 0

def set_balance_db(conn, user_id: int, balance: int):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO users(user_id, balance) VALUES(?, ?)
    ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance
    """, (user_id, balance))
    conn.commit()
    
def record_event_service(
    user_id: int,
    amount: int,
    event_type: Literal["reward", "penalty"],
    reason: str,
    source: Literal["user", "supervisor", "agent"] = "user",
    evidence_id: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        ensure_user(conn, user_id)

        balance_before = get_balance_db(conn, user_id)
        change = amount if event_type == "reward" else -amount
        if balance_before + change < 0:
            conn.rollback()
            return {"ok": False, "error": "余额不足，不能扣到负数"}

        balance_after = balance_before + change
        set_balance_db(conn, user_id, balance_after)

        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        cur = conn.cursor()
        cur.execute(""" ... """, (...))

        conn.commit()
        return {...}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_balance_service(user_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        ensure_user(conn, user_id)
        return {"user_id": user_id, "balance": get_balance_db(conn, user_id)}
    finally:
        conn.close()

def get_history_service(user_id: int, limit: int = 20) -> Dict[str, Any]:
    conn = get_conn()
    try:
        ensure_user(conn, user_id)
        limit = max(1, min(limit, 200))
        cur = conn.cursor()
        cur.execute("""
        SELECT * FROM ledger
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """, (user_id, limit))
        rows = [dict(r) for r in cur.fetchall()]
        return {"user_id": user_id, "count": len(rows), "items": rows}
    finally:
        conn.close()
# ed
