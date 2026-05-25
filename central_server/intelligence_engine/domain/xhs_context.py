from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

XHS_BASE_URL = "https://www.xiaohongshu.com"


@dataclass(frozen=True)
class XhsNoteContext:
    note_id: str
    xsec_token: str = ""
    xsec_source: str = ""

    @property
    def has_xsec_context(self) -> bool:
        return bool(self.xsec_token and self.xsec_source)

    def to_payload(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "xsec_token": self.xsec_token,
            "xsec_source": self.xsec_source,
            "has_xsec_context": self.has_xsec_context,
        }


def normalize_xhs_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return urljoin(XHS_BASE_URL, url)


def parse_xhs_note_context(url: str | None) -> XhsNoteContext | None:
    normalized = normalize_xhs_url(url)
    if not normalized:
        return None
    parsed = urlparse(normalized)
    path_parts = [part for part in parsed.path.split("/") if part]
    note_id = ""
    for index, part in enumerate(path_parts):
        if part in {"explore", "item"} and index + 1 < len(path_parts):
            note_id = path_parts[index + 1]
            break
    if not note_id and path_parts:
        tail = path_parts[-1]
        if tail not in {"explore", "discovery", "item"}:
            note_id = tail
    if not note_id:
        return None
    params = parse_qs(parsed.query, keep_blank_values=True)
    return XhsNoteContext(
        note_id=note_id,
        xsec_token=(params.get("xsec_token") or [""])[0],
        xsec_source=(params.get("xsec_source") or [""])[0],
    )


def merge_xhs_context(*contexts: dict[str, Any] | XhsNoteContext | None) -> dict[str, Any]:
    merged = {"note_id": "", "xsec_token": "", "xsec_source": "", "has_xsec_context": False}
    for context in contexts:
        if context is None:
            continue
        payload = context.to_payload() if isinstance(context, XhsNoteContext) else context
        if not isinstance(payload, dict):
            continue
        note_id = payload.get("note_id")
        if note_id and not merged["note_id"]:
            merged["note_id"] = note_id
        for key in ("xsec_token", "xsec_source"):
            value = payload.get(key)
            if value:
                merged[key] = value
    merged["has_xsec_context"] = bool(merged["xsec_token"] and merged["xsec_source"])
    return merged


def context_from_url_and_raw(url: str | None, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = raw or {}
    parsed = parse_xhs_note_context(url)
    return merge_xhs_context(
        parsed,
        raw.get("platform_context") if isinstance(raw.get("platform_context"), dict) else None,
        {
            "note_id": raw.get("note_id") or raw.get("platform_content_id"),
            "xsec_token": raw.get("xsec_token"),
            "xsec_source": raw.get("xsec_source"),
        },
    )


def url_has_xsec_context(url: str | None) -> bool:
    context = parse_xhs_note_context(url)
    return bool(context and context.has_xsec_context)


def prefer_richer_xhs_url(existing: str | None, candidate: str | None) -> str | None:
    if not existing:
        return candidate
    if not candidate:
        return existing
    existing_context = parse_xhs_note_context(existing)
    candidate_context = parse_xhs_note_context(candidate)
    if candidate_context and candidate_context.has_xsec_context:
        return candidate
    if not (existing_context and existing_context.has_xsec_context):
        return candidate
    return existing


def build_xhs_note_url(context: dict[str, Any], *, fallback_url: str | None = None) -> str | None:
    note_id = context.get("note_id") or ""
    if not note_id:
        return fallback_url
    base_url = f"{XHS_BASE_URL}/explore/{note_id}"
    query = {}
    if context.get("xsec_token"):
        query["xsec_token"] = context["xsec_token"]
    if context.get("xsec_source"):
        query["xsec_source"] = context["xsec_source"]
    if not query:
        return fallback_url or base_url
    return f"{base_url}?{urlencode(query)}"
