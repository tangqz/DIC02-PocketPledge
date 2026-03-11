import hashlib
import secrets
import sys
import importlib.util
from pathlib import Path

# Manually load the module to avoid importing parent packages that might have heavy dependencies
def load_security_module():
    path = Path(__file__).parents[1] / "app" / "auth" / "security.py"
    spec = importlib.util.spec_from_file_location("security_standalone", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

security = load_security_module()
hash_password = security.hash_password
verify_password = security.verify_password

def test_hash_password_format():
    password = "secret_password"
    hashed = hash_password(password)
    assert hashed.startswith("pbkdf2:sha256:260000$")
    parts = hashed.split("$")
    assert len(parts) == 3
    # salt and dk should be hex strings
    int(parts[1], 16)
    int(parts[2], 16)

def test_verify_password_correct():
    password = "secret_password"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True

def test_verify_password_incorrect():
    password = "secret_password"
    hashed = hash_password(password)
    assert verify_password("wrong_password", hashed) is False

def test_verify_password_malformed_hash():
    password = "secret_password"
    assert verify_password(password, "invalid_hash") is False
    assert verify_password(password, "pbkdf2:sha256:260000$nothex$nothex") is False
    assert verify_password(password, "pbkdf2:sha256:notint$abc$def") is False

def test_verify_password_different_iterations():
    # Manual creation of a hash with different iterations
    password = "secret_password"
    iterations = 1000
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    hashed = f"pbkdf2:sha256:{iterations}${salt.hex()}${dk.hex()}"

    assert verify_password(password, hashed) is True
    assert verify_password("wrong", hashed) is False

def test_verify_password_edge_cases():
    assert verify_password("", hash_password("")) is True
    assert verify_password(" ", hash_password(" ")) is True
    assert verify_password("a" * 100, hash_password("a" * 100)) is True
