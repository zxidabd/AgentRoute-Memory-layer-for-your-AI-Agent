"""JWT and password security utilities for production authentication."""

import hashlib
import hmac as _hmac
import secrets
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from jose import jwt, JWTError

from ..config import settings


def hash_password(password: str) -> str:
    """Hash password using bcrypt directly."""
    pw_bytes = password.encode('utf-8')[:72]  # bcrypt max 72 bytes
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash. Also supports legacy PBKDF2 hashes."""
    if not hashed_password:
        return False
    # Support legacy PBKDF2 format (salt:key)
    if ":" in hashed_password and not hashed_password.startswith("$"):
        salt, key = hashed_password.split(":", 1)
        new_key = hashlib.pbkdf2_hmac(
            'sha256', plain_password.encode('utf-8'),
            salt.encode('utf-8'), 100000
        ).hex()
        return _hmac.compare_digest(key, new_key)
    # bcrypt verification
    try:
        pw_bytes = plain_password.encode('utf-8')[:72]
        return bcrypt.checkpw(pw_bytes, hashed_password.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: str,
    org_id: str,
    role: str,
    remember_me: bool = False
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if remember_me:
        expire = now + timedelta(days=30)
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "iat": now,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token string."""
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash of the refresh token for storage."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_email_verification_token(user_id: str) -> str:
    """Generate high-entropy cryptographic token for email verification."""
    raw_secret = secrets.token_urlsafe(48)
    return f"emv_{user_id}_{raw_secret}"


def hash_email_token(token: str) -> str:
    """SHA-256 hash of email verification token."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

