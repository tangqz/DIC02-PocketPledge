"""JWT token utilities and password hashing for multi-user authentication."""

import os
import logging
from datetime import datetime, timedelta, timezone

import hashlib
import hmac
import secrets
import json
import base64

# ── Configuration ──

logger = logging.getLogger(__name__)

_DEV_FALLBACK_SECRET_KEY = "dic2026-local-dev-secret-change-me"


def _resolve_secret_key() -> str:
    configured = (os.getenv("AUTH_SECRET_KEY") or "").strip()
    if configured:
        return configured

    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()
    if app_env in {"prod", "production"}:
        raise RuntimeError("AUTH_SECRET_KEY must be set in production")

    logger.warning(
        "AUTH_SECRET_KEY is not set; using an insecure local development fallback. "
        "Set AUTH_SECRET_KEY in backend/.env to keep tokens stable across restarts."
    )
    return _DEV_FALLBACK_SECRET_KEY


SECRET_KEY = _resolve_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440")
)  # 24h default
INITIAL_BALANCE = int(os.getenv("AUTH_INITIAL_BALANCE", "3000"))


# ── Password hashing (PBKDF2-SHA256, stdlib only) ──

_PBKDF2_ITERATIONS = 260_000
_SALT_BYTES = 16

# 🛡️ Sentinel: Mitigate User Enumeration Timing Attacks during login
# Pre-computed dummy hash matching the application's hashing algorithm format.
# When a user is not found, verify against this so the verifier still does the expensive PBKDF2 hash.
DUMMY_HASH = f"pbkdf2:sha256:{_PBKDF2_ITERATIONS}${0:032x}${0:064x}"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2:sha256:{_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        header, salt_hex, dk_hex = hashed.split("$")
        iterations = int(header.split(":")[-1])
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ── JWT (minimal implementation, stdlib only) ──


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_access_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    header = _b64url_encode(json.dumps({"alg": ALGORITHM, "typ": "JWT"}).encode())
    payload = _b64url_encode(
        json.dumps(
            {
                "sub": str(user_id),
                "username": username,
                "exp": int(expire.timestamp()),
                "iat": int(now.timestamp()),
            }
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = hmac.new(
        SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict | None:
    """Decode and verify a JWT token. Returns payload dict or None if invalid."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        exp = payload.get("exp", 0)
        if datetime.now(timezone.utc).timestamp() > exp:
            return None
        return payload
    except Exception:
        return None
