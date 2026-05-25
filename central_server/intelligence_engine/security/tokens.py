from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class TokenError(Exception):
    pass


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def create_access_token(*, user_id: str, roles: list[str], secret: str, ttl_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": user_id, "roles": roles, "iat": now, "exp": now + ttl_seconds}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("invalid token format") from exc
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_decode(signature_b64), expected):
        raise TokenError("invalid token signature")
    payload = json.loads(_b64url_decode(payload_b64))
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise TokenError("token expired")
    if not payload.get("sub"):
        raise TokenError("missing subject")
    return payload
