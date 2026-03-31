from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"


def _prepare_import_path() -> None:
    if not BACKEND_DIR.exists():
        raise RuntimeError(f"backend directory not found: {BACKEND_DIR}")
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def _build_default_database_url() -> str:
    # Keep path resolution relative to project structure so the script works for all deployments.
    db_path = (BACKEND_DIR / "reward.db").resolve()
    return f"sqlite:///{db_path.as_posix()}"


def _parse_amount_to_fen(raw_amount: str, unit: str) -> int:
    text = raw_amount.strip()
    if not text:
        raise ValueError("amount cannot be empty")

    if unit == "fen":
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("amount must be an integer when unit=fen") from exc
        if value <= 0:
            raise ValueError("amount must be greater than 0")
        return value

    try:
        yuan = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("amount must be a valid decimal when unit=yuan") from exc

    if yuan <= 0:
        raise ValueError("amount must be greater than 0")

    fen = int((yuan * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))
    if fen <= 0:
        raise ValueError("amount is too small after conversion to fen")
    return fen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Debug wallet top-up tool (run from repository root)."
    )
    parser.add_argument("user_id", type=int, help="Target user ID")
    parser.add_argument("amount", help="Top-up amount. Use decimal for yuan")
    parser.add_argument(
        "--unit",
        choices=["yuan", "fen"],
        default="yuan",
        help="Amount unit: yuan (default) or fen",
    )
    parser.add_argument(
        "--reason",
        default="Debug top-up via root script",
        help="Transaction reason",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Optional DATABASE_URL override. If not provided, uses env or backend/reward.db",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    _prepare_import_path()

    if args.database_url.strip():
        os.environ["DATABASE_URL"] = args.database_url.strip()
    else:
        os.environ.setdefault("DATABASE_URL", _build_default_database_url())

    from app.business.crud import get_user_status, topup_wallet
    from app.business.models import SessionLocal, init_db

    try:
        amount_fen = _parse_amount_to_fen(args.amount, args.unit)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 2

    init_db()

    db = SessionLocal()
    try:
        before = get_user_status(db, args.user_id)
        result = topup_wallet(
            db=db,
            user_id=args.user_id,
            amount=amount_fen,
            reason=args.reason,
        )
        after = get_user_status(db, args.user_id)
    except Exception as exc:
        print(f"[ERROR] top-up failed: {exc}")
        return 1
    finally:
        db.close()

    print("[OK] top-up completed")
    print(f"user_id: {args.user_id}")
    print(f"amount_fen: {amount_fen}")
    print(f"amount_yuan: {amount_fen / 100:.2f}")
    print(f"balance_before_fen: {before['balance']}")
    print(f"balance_after_fen: {after['balance']}")
    print(f"tx_id: {result['tx_id']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())