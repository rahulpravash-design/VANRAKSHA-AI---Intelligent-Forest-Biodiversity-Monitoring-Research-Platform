"""Password hashing and JWT handling.

Password hashes are self-describing strings ``<scheme>$<parameters>``:

* ``bcrypt$<hash>``                                  – preferred, used when the
  ``bcrypt`` package is installed.
* ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`` – pure-stdlib fallback so
  the API still runs (and the test suite still passes) without native wheels.

Existing hashes keep verifying after a scheme change, and
:func:`needs_rehash` tells the auth service when to transparently upgrade a
stored hash on the user's next successful login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.config import settings

try:  # pragma: no cover - depends on the installed environment
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover
    _bcrypt = None

PBKDF2_ITERATIONS = 390_000
_PREFERRED_SCHEME = "bcrypt" if _bcrypt is not None else "pbkdf2_sha256"

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------- #
# password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash a plaintext password with the strongest available scheme."""
    if not password:
        raise ValueError("password must not be empty")
    if _bcrypt is not None:
        # bcrypt truncates at 72 bytes; pre-hash so long passphrases keep entropy.
        digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
        return "bcrypt$" + _bcrypt.hashpw(digest, _bcrypt.gensalt(rounds=12)).decode()
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time verification that dispatches on the stored scheme."""
    if not password or not stored or "$" not in stored:
        return False
    scheme, _, rest = stored.partition("$")
    try:
        if scheme == "bcrypt":
            if _bcrypt is None:
                return False
            digest = base64.b64encode(hashlib.sha256(password.encode()).digest())
            return _bcrypt.checkpw(digest, rest.encode())
        if scheme == "pbkdf2_sha256":
            iterations_raw, salt_hex, expected_hex = rest.split("$")
            derived = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations_raw)
            )
            return hmac.compare_digest(derived.hex(), expected_hex)
    except (ValueError, TypeError):
        return False
    return False


def needs_rehash(stored: str | None) -> bool:
    """True when a stored hash uses an older scheme than we now prefer."""
    if not stored or "$" not in stored:
        return True
    return stored.partition("$")[0] != _PREFERRED_SCHEME


def validate_password_strength(password: str) -> list[str]:
    """Return a list of human-readable problems; empty means acceptable."""
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters long")
    if not any(c.isalpha() for c in password):
        problems.append("must contain at least one letter")
    if not any(c.isdigit() for c in password):
        problems.append("must contain at least one digit")
    if password.lower() in {"password", "vanraksha", "12345678901", "qwertyuiop"}:
        problems.append("is too common")
    return problems


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token(
    subject: str | int,
    token_type: TokenType,
    *,
    role: str | None = None,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    """Create a signed JWT.

    Returns ``(token, jti, expires_at)`` — the ``jti`` lets the caller revoke the
    token later (see :class:`app.models.auth.RevokedToken`).
    """
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.access_token_expire_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_expire_days)
        )
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": "vanraksha-ai",
    }
    if role:
        payload["role"] = role
    if extra_claims:
        payload.update(extra_claims)
    return _encode(payload), jti, now + expires_delta


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a JWT. Raises :class:`jwt.PyJWTError` when invalid."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer="vanraksha-ai",
        options={"require": ["exp", "sub", "type"]},
    )
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return payload


__all__ = [
    "create_token",
    "decode_token",
    "hash_password",
    "needs_rehash",
    "validate_password_strength",
    "verify_password",
]
