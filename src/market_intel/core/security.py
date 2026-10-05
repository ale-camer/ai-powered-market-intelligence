"""Security utilities for JWT token creation, decoding, and verification."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

from market_intel.core.config import get_settings
from market_intel.core.logger import get_logger

logger = get_logger("market_intel.core.security")

try:
    import jwt

    _HAS_PYJWT = True
except ImportError:
    _HAS_PYJWT = False


def _base64url_encode(data: bytes) -> str:
    """Encode bytes to a base64url string without trailing padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    """Decode a base64url string, automatically handling missing padding."""
    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("ascii"))


def create_access_token(
    data: dict[str, object],
    secret_key: str | None = None,
    expires_in: int | None = None,
) -> str:
    """Create a signed RFC 7519 HS256 JWT access token.

    Args:
        data: Claims payload dictionary to include in the token.
        secret_key: HMAC secret key (defaults to Settings.secret_key).
        expires_in: Expiration lifetime in seconds (defaults to Settings.jwt_expiration_seconds).

    Returns:
        Encoded and signed JWT string.
    """
    settings = get_settings()
    key = secret_key or settings.secret_key
    lifetime = expires_in if expires_in is not None else settings.jwt_expiration_seconds
    now_ts = int(datetime.now(UTC).timestamp())

    payload = dict(data)
    if "exp" not in payload:
        payload["exp"] = now_ts + lifetime
    if "iat" not in payload:
        payload["iat"] = now_ts

    if _HAS_PYJWT:
        return str(jwt.encode(payload, key, algorithm="HS256"))

    # Pure standard library RFC 7519 HS256 implementation
    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_b64 = _base64url_encode(header_json)
    payload_b64 = _base64url_encode(payload_json)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_access_token(
    token: str,
    secret_key: str | None = None,
) -> dict[str, object] | None:
    """Verify and decode a signed HS256 JWT token.

    Args:
        token: JWT string to verify.
        secret_key: HMAC secret key (defaults to Settings.secret_key).

    Returns:
        Decoded claims dictionary if signature and expiration are valid; None otherwise.
    """
    if not token or not isinstance(token, str):
        return None

    settings = get_settings()
    key = secret_key or settings.secret_key

    if _HAS_PYJWT:
        try:
            decoded: dict[str, object] = jwt.decode(token, key, algorithms=["HS256"])
            return decoded
        except Exception as exc:
            logger.debug(f"PyJWT token verification failed: {exc}")
            return None

    # Pure standard library RFC 7519 verification
    parts = token.split(".")
    if len(parts) != 3:
        logger.debug("Token does not have 3 segments")
        return None

    header_b64, payload_b64, sig_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_sig_b64 = _base64url_encode(expected_sig)

    if not hmac.compare_digest(expected_sig_b64, sig_b64):
        logger.debug("Token signature verification failed")
        return None

    try:
        payload_bytes = _base64url_decode(payload_b64)
        raw_payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(raw_payload, dict):
            return None
    except Exception as exc:
        logger.debug(f"Failed to decode token payload JSON: {exc}")
        return None

    # Check expiration claim if present
    if "exp" in raw_payload:
        exp_val = raw_payload["exp"]
        if isinstance(exp_val, (int, float)):
            now_ts = int(datetime.now(UTC).timestamp())
            if now_ts >= exp_val:
                logger.debug(f"Token expired at {exp_val} (current: {now_ts})")
                return None

    return raw_payload
