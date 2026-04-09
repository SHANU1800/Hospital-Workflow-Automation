"""Security utilities for password hashing and JWT token handling."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict

from jose import JWTError, jwt

PBKDF2_ITERATIONS = 390000


def get_jwt_secret_key() -> str:
    """Return JWT secret from environment with a safe dev default."""
    return os.getenv("JWT_SECRET_KEY", "change-this-in-production")


def get_jwt_algorithm() -> str:
    """Return JWT signing algorithm from environment."""
    return os.getenv("JWT_ALGORITHM", "HS256")


def get_jwt_expire_minutes() -> int:
    """Return access token expiration (minutes)."""
    raw = os.getenv("JWT_EXPIRE_MINUTES", "60")
    try:
        minutes = int(raw)
        return max(minutes, 1)
    except ValueError:
        return 60


def validate_jwt_config() -> None:
    """Validate JWT configuration at startup."""
    secret = get_jwt_secret_key()
    if not secret or secret.strip() == "":
        raise ValueError("JWT_SECRET_KEY is required and cannot be empty")


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against its hash."""
    try:
        algo, iterations, salt, digest = hashed_password.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False

        computed = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(computed, digest)
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_minutes: int | None = None) -> str:
    """Create signed JWT access token."""
    expire_in = expires_minutes if expires_minutes is not None else get_jwt_expire_minutes()
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=expire_in)})
    return jwt.encode(to_encode, get_jwt_secret_key(), algorithm=get_jwt_algorithm())


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[get_jwt_algorithm()])
        return payload
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
