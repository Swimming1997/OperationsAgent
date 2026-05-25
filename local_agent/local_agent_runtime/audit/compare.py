from __future__ import annotations

import difflib
import re
from typing import Any
from urllib.parse import urlparse


def field_coverage(items: list[dict[str, Any]] | list[Any], fields: list[str]) -> dict[str, float]:
    if not fields:
        return {}
    if not items:
        return {field: 0.0 for field in fields}
    result: dict[str, float] = {}
    for field in fields:
        count = 0
        for item in items:
            value = item.get(field) if isinstance(item, dict) else getattr(item, field, None)
            if value not in (None, "", [], {}):
                count += 1
        result[field] = round(count / len(items), 3)
    return result


def _norm_text(value: Any) -> str:
    return re.sub(r"\\s+", "", str(value or "")).lower()


def compare_text(expected: Any, actual: Any) -> bool:
    left = _norm_text(expected)
    right = _norm_text(actual)
    if not left and not right:
        return True
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    return difflib.SequenceMatcher(None, left, right).ratio() >= 0.72


def _count_to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("k") or text.endswith("K"):
        multiplier = 1000
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def compare_count(expected: Any, actual: Any, *, tolerance_ratio: float = 0.08, tolerance_abs: int = 3) -> bool:
    left = _count_to_number(expected)
    right = _count_to_number(actual)
    if left is None or right is None:
        return left == right
    return abs(left - right) <= max(tolerance_abs, abs(left) * tolerance_ratio)


def _note_id_from_url(value: str) -> str:
    path = urlparse(value).path
    parts = [part for part in path.split("/") if part]
    for marker in ("explore", "item"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return parts[-1] if parts else value


def compare_url(expected: Any, actual: Any) -> bool:
    if not expected or not actual:
        return expected == actual
    return _note_id_from_url(str(expected)) == _note_id_from_url(str(actual))
