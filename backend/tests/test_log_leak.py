from fastapi.testclient import TestClient
from app.main import app
import logging


def test_log_leak(caplog):
    caplog.set_level(logging.INFO)
    client = TestClient(app)

    # Make a request with a token in query
    client.get("/ws?token=secret_jwt_token_here")

    found_rx = False
    for record in caplog.records:
        if "http rx" in record.getMessage():
            found_rx = True
            print(f"Log Output: {record.getMessage()}")
            assert "secret_jwt_token_here" not in record.getMessage(), (
                "Token leaked in logs!"
            )
            assert "token=***" in record.getMessage(), "Token not properly masked"

    assert found_rx, "Did not find http rx log"
