"""RFC 6238 compliant Two-Factor Authentication (TOTP) module.

Zero external dependencies - standard library implementation.
Compatible with Google Authenticator, Authy, Microsoft Authenticator, 1Password.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret() -> str:
    """Generates a random 160-bit base32 encoded secret key."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").replace("=", "")


def get_totp_code(secret: str, time_step: int = 30) -> str:
    """Generates the current 6-digit TOTP code for a given secret."""
    padded_secret = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    counter = int(time.time() // time_step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[19] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def verify_totp_code(secret: str, code: str, window: int = 1, time_step: int = 30) -> bool:
    """Verifies a 6-digit TOTP code against a secret with clock-drift window support."""
    if not secret or not code:
        return False
    clean_code = str(code).strip()
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False

    padded_secret = secret + "=" * ((8 - len(secret) % 8) % 8)
    try:
        key = base64.b32decode(padded_secret, casefold=True)
    except Exception:
        return False

    current_t = int(time.time() // time_step)
    for delta in range(-window, window + 1):
        counter = current_t + delta
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[19] & 0x0F
        expected = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
        if f"{expected:06d}" == clean_code:
            return True
    return False


def get_totp_uri(secret: str, email: str, issuer: str = "AgentRoute") -> str:
    """Generates the standard otpauth URI for QR code generation."""
    encoded_issuer = quote(issuer)
    encoded_email = quote(email)
    return f"otpauth://totp/{encoded_issuer}:{encoded_email}?secret={secret}&issuer={encoded_issuer}&algorithm=SHA1&digits=6&period=30"
