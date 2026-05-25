from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

XHS_BASE_URL = "https://www.xiaohongshu.com"

SUSPECT_DETAIL_AUTHOR_NAMES = frozenset({"我", "Me", "me"})


@dataclass(frozen=True)
class XhsNoteContext:
    note_id: str
    xsec_token: str = ""
    xsec_source: str = ""

    @property
    def has_xsec_context(self) -> bool:
        return bool(self.xsec_token)

    def to_payload(self) -> dict[str, Any]:
        return enrich_xhs_platform_context(
            {
                "note_id": self.note_id,
                "xsec_token": self.xsec_token,
                "xsec_source": self.xsec_source,
            }
        )


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
    for idx, part in enumerate(path_parts):
        if part in {"explore", "item"} and idx + 1 < len(path_parts):
            note_id = path_parts[idx + 1]
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


def infer_xsec_source(*, xsec_source: str = "", source_surface: str | None = None) -> tuple[str, str, bool]:
    if xsec_source:
        return xsec_source, "provided", False
    surface = (source_surface or "").lower()
    if surface in {"xhs_home_feed", "homefeed", "xhs.feed.home_recommend"}:
        return "pc_feed", "inferred_from_homefeed", True
    if surface in {"search", "xhs.search.notes", "search_api"}:
        return "pc_search", "inferred_from_search", True
    return "pc_search", "default_pc_search", True


def enrich_xhs_platform_context(context: dict[str, Any] | None, *, source_surface: str | None = None) -> dict[str, Any]:
    payload = dict(context or {})
    note_id = str(payload.get("note_id") or "").strip()
    xsec_token = str(payload.get("xsec_token") or "").strip()
    xsec_source = str(payload.get("xsec_source") or "").strip()
    effective, status, inferred = infer_xsec_source(xsec_source=xsec_source, source_surface=source_surface or payload.get("source_surface"))
    payload.update(
        {
            "note_id": note_id,
            "xsec_token": xsec_token,
            "xsec_source": xsec_source,
            "has_note_id": bool(note_id),
            "has_xsec_token": bool(xsec_token),
            "has_xsec_source": bool(xsec_source),
            "api_detail_ready": bool(note_id and xsec_token),
            "api_comment_ready": bool(note_id and xsec_token),
            "xsec_source_effective": effective,
            "xsec_source_status": status,
            "xsec_source_inferred": inferred,
            "has_xsec_context": bool(xsec_token),
        }
    )
    if source_surface:
        payload["source_surface"] = source_surface
    return payload


def merge_xhs_context(*contexts: dict[str, Any] | XhsNoteContext | None, source_surface: str | None = None) -> dict[str, Any]:
    merged: dict[str, Any] = {"note_id": "", "xsec_token": "", "xsec_source": ""}
    for context in contexts:
        if context is None:
            continue
        payload = context.to_payload() if isinstance(context, XhsNoteContext) else context
        if not isinstance(payload, dict):
            continue
        note_id = payload.get("note_id")
        if note_id and not merged["note_id"]:
            merged["note_id"] = note_id
        for key in ("xsec_token", "xsec_source", "source_surface"):
            value = payload.get(key)
            if value:
                merged[key] = value
    return enrich_xhs_platform_context(merged, source_surface=source_surface or merged.get("source_surface"))


def context_from_url_and_raw(url: str | None, raw: dict[str, Any] | None = None, *, source_surface: str | None = None) -> dict[str, Any]:
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
        source_surface=source_surface,
    )


def url_has_xsec_context(url: str | None) -> bool:
    context = parse_xhs_note_context(url)
    return bool(context and context.xsec_token)


def prefer_richer_xhs_url(existing: str | None, candidate: str | None) -> str | None:
    if not existing:
        return candidate
    if not candidate:
        return existing
    existing_context = parse_xhs_note_context(existing)
    candidate_context = parse_xhs_note_context(candidate)
    if candidate_context and candidate_context.xsec_token:
        return candidate
    if not (existing_context and existing_context.xsec_token):
        return candidate
    return existing


def build_xhs_note_url(
    context: dict[str, Any],
    *,
    fallback_url: str | None = None,
    source_surface: str | None = None,
) -> str | None:
    enriched = enrich_xhs_platform_context(context, source_surface=source_surface)
    note_id = enriched.get("note_id") or ""
    if not note_id:
        return fallback_url
    base_url = f"{XHS_BASE_URL}/explore/{note_id}"
    query: dict[str, str] = {}
    if enriched.get("xsec_token"):
        query["xsec_token"] = str(enriched["xsec_token"])
        xsec_source = enriched.get("xsec_source") or enriched.get("xsec_source_effective")
        if xsec_source:
            query["xsec_source"] = str(xsec_source)
    if not query:
        return fallback_url or base_url
    return f"{base_url}?{urlencode(query)}"


def is_suspect_detail_author_name(author_name: str | None, *, upstream_author_name: str | None = None) -> bool:
    text = str(author_name or "").strip()
    if not text:
        return False
    if text in SUSPECT_DETAIL_AUTHOR_NAMES:
        return True
    upstream = str(upstream_author_name or "").strip()
    return bool(upstream and text != upstream)


async def enrich_xhs_context_from_page(page, *, url: str, note_id: str, platform_context: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    context = merge_xhs_context(platform_context or {}, context_from_url_and_raw(url), {"note_id": note_id})
    if context.get("api_detail_ready"):
        return build_xhs_note_url(context, fallback_url=url) or url, context
    target = build_xhs_note_url(context, fallback_url=url) or url
    try:
        await page.goto(target, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        enriched = merge_xhs_context(context, context_from_url_and_raw(page.url), {"note_id": note_id})
        resolved = build_xhs_note_url(enriched, fallback_url=page.url) or page.url
        return resolved, enriched
    except Exception:
        return url, context
