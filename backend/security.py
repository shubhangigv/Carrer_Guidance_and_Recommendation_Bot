"""Passwords and login tokens.

* Passwords are hashed with bcrypt (the bcrypt package directly; passlib has problems on Python 3.13).
  Only the hash is stored, never the password.
* After login the student gets a JWT (JSON Web Token): a signed string that says "student 7, valid
  until 15:30". Protected endpoints check the signature and the expiry.

Settings come from .env:  JWT_SECRET (a long random string), JWT_EXPIRE_MINUTES (default 60).
Make a secret in PowerShell:  python -c "import secrets; print(secrets.token_urlsafe(48))"
"""
import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv

from backend.db import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

ALGORITHM = "HS256"
_fallback_secret = None


def jwt_secret():
    """JWT_SECRET from .env. If it is missing, use a random one for this run only (tokens stop
    working when the server restarts) and warn, so development still works."""
    global _fallback_secret
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    if _fallback_secret is None:
        warnings.warn("JWT_SECRET is not set in .env - using a temporary random secret.")
        _fallback_secret = secrets.token_urlsafe(48)
    return _fallback_secret


def expire_minutes():
    return int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:                      # malformed hash or a password over 72 bytes
        return False


def create_token(student_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(student_id), "iat": now, "exp": now + timedelta(minutes=expire_minutes())}
    return jwt.encode(payload, jwt_secret(), algorithm=ALGORITHM)


def read_token(token: str) -> int:
    """The student id inside a valid token. Raises jwt.InvalidTokenError if it is wrong or expired."""
    payload = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
    return int(payload["sub"])
