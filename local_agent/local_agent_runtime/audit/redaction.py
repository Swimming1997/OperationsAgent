from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_KEYS = {"cookie", "authorization", "x-s", "x-t", "x-s-common", "xsec_token", "phone", "验证码"}
TOKEN_RE = re.compile(r"(xsec_token=)([^&\s]+)", re.IGNORECASE)
ENCODED_TOKEN_RE = re.compile(r"(xsec_token(?:%3D|%3d|=))(.+?)(?=%26(?:xsec|xsec_source)|&|$)", re.IGNORECASE)
HEADER_RE = re.compile(r"\b(cookie|authorization|x-s|x-t|x-s-common)\b\s*[:=]\s*[^,;\n\r]+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower() == "xsec_token":
                query.append((key, _mask(value)))
            else:
                query.append((key, value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, safe="*"), parts.fragment))
    except Exception:
        return TOKEN_RE.sub(lambda match: match.group(1) + _mask(match.group(2)), url)


def redact_text(text: str) -> str:
    value = TOKEN_RE.sub(lambda match: match.group(1) + _mask(match.group(2)), text)
    value = ENCODED_TOKEN_RE.sub(lambda match: match.group(1) + _mask(match.group(2)), value)
    value = HEADER_RE.sub(lambda match: f"{match.group(1)}: ***", value)
    value = PHONE_RE.sub("***PHONE***", value)
    value = value.replace("验证码", "***")
    return value


def redact_mapping(payload: dict) -> dict:
    def redact_value(key: str, value: Any) -> Any:
        key_lower = key.lower()
        if key_lower in SENSITIVE_KEYS:
            return _mask(str(value))
        if isinstance(value, dict):
            return {str(k): redact_value(str(k), v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact_value(key, item) for item in value]
        if isinstance(value, str):
            if value.startswith("http"):
                return redact_text(redact_url(value))
            return redact_text(value)
        return value

    return {str(key): redact_value(str(key), value) for key, value in payload.items()}
