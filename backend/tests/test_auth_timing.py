import time
from app.auth.routes import login
from app.auth.schemas import LoginRequest
from app.business.models import User, get_db, init_db
from fastapi import HTTPException
import os
import sqlite3

def test_login_timing():
    # Use an in-memory db just for this test
    # but the init_db actually creates a file by default if we use get_db
    # we'll just mock db or use a real db
    init_db()
    db = next(get_db())

    # Insert a real user
    user = User(username="timinguser", email="timing@test.com", password_hash="pbkdf2:sha256:260000$00000000000000000000000000000000$0000000000000000000000000000000000000000000000000000000000000000", role="user")

    # Just in case it already exists
    try:
        db.add(user)
        db.commit()
    except Exception:
        db.rollback()

    try:
        req_valid = LoginRequest(username="timinguser", password="wrongpassword")
        req_invalid = LoginRequest(username="nonexistent", password="wrongpassword")

        # Time existing user
        t0 = time.time()
        try:
            login(req_valid, db)
        except HTTPException:
            pass
        t1 = time.time()
        time_existing = t1 - t0

        # Time non-existent user
        t0 = time.time()
        try:
            login(req_invalid, db)
        except HTTPException:
            pass
        t1 = time.time()
        time_nonexistent = t1 - t0

        # Ensure times are within 0.1s of each other (should be virtually identical)
        assert abs(time_existing - time_nonexistent) < 0.1
    finally:
        # Cleanup
        real_user = db.query(User).filter_by(username="timinguser").first()
        if real_user:
            db.delete(real_user)
            db.commit()
