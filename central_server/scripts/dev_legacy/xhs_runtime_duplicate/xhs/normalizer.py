from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

from intelligence_engine.domain.enums import ContentType, FeedType, Platform, SourceSurface
from intelligence_engine.domain.schemas import FeedCandidateInput
from intelligence_engine.connectors.xhs.context import context_from_url_and_raw, normalize_xhs_url
from intelligence_engine.storage.repositories.content_repository import sanitize_feed_author_name

CONTENT_ID_PATTERNS = [
    re.compile(r"/explore/([0-9a-zA-Z]+)"),
    re.compile(r"/discovery/item/([0-9a-zA-Z]+)"),
]


def parse_visible_count(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip().replace(",", "")
    if not text:
        return None
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.lower().endswith("k"):
        multiplier = 1000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        digits = re.findall(r"\d+", text)
        return int("".join(digits)) if digits else None


def extract_xhs_content_id(url: str | None) -> str | None:
    if not url:
        return None
    for pattern in CONTENT_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    parsed = urlparse(url)
    if parsed.path:
        tail = parsed.path.rstrip("/").split("/")[-1]
        if tail and tail not in {"explore", "discovery"}:
            return tail
    return None


def infer_content_type(raw: dict[str, Any]) -> ContentType:
    text = " ".join(str(raw.get(key) or "") for key in ["href", "card_class", "card_text", "cover_url"]).lower()
    if "video" in text or "视频" in text:
        return ContentType.VIDEO
    return ContentType.IMAGE_TEXT


def normalize_xhs_search_card(
    raw: dict[str, Any],
    *,
    search_keyword: str,
    rank_position: int,
    discovered_at: datetime | None = None,
) -> FeedCandidateInput | None:
    candidate = normalize_xhs_card(raw, feed_position=rank_position, discovered_at=discovered_at)
    if not candidate:
        return None
    context = dict(candidate.platform_context or {})
    if not context.get("xsec_source"):
        context["xsec_source"] = "pc_search"
        context["has_xsec_context"] = bool(context.get("xsec_token"))
    payload = dict(candidate.raw_payload or {})
    payload["search_keyword"] = search_keyword
    payload["search_keywords"] = [search_keyword]
    payload["rank_position"] = rank_position
    return candidate.model_copy(
        update={
            "source_surface": SourceSurface.SEARCH,
            "feed_type": None,
            "feed_position": rank_position,
            "platform_context": context,
            "raw_payload": payload,
        }
    )


def normalize_xhs_card(raw: dict[str, Any], *, feed_position: int, discovered_at: datetime | None = None) -> FeedCandidateInput | None:
    href = raw.get("href") or raw.get("canonical_url")
    canonical_url = normalize_xhs_url(href)
    platform_context = context_from_url_and_raw(canonical_url, raw)
    if platform_context.get("xsec_token") and not platform_context.get("xsec_source"):
        platform_context["xsec_source"] = "pc_feed"
        platform_context["has_xsec_context"] = True
    platform_content_id = raw.get("platform_content_id") or platform_context.get("note_id") or extract_xhs_content_id(canonical_url)
    if not platform_content_id:
        return None
    return FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id=platform_content_id,
        canonical_url=canonical_url,
        content_type=infer_content_type(raw),
        title_or_summary=raw.get("title") or raw.get("title_or_summary"),
        cover_url=raw.get("cover_url"),
        author_platform_id=raw.get("author_platform_id"),
        author_name=sanitize_feed_author_name(raw.get("author_name")),
        visible_like_count=parse_visible_count(raw.get("visible_like_count")),
        source_surface=SourceSurface.XHS_HOME_FEED,
        feed_type=FeedType.XHS_HOME_FEED,
        feed_position=feed_position,
        discovered_at=discovered_at or datetime.now(timezone.utc),
        raw_payload=raw,
        platform_context=platform_context,
    )


def candidate_field_report(candidates: list[FeedCandidateInput], *, target_count: int) -> dict[str, Any]:
    fields = [
        "platform_content_id",
        "canonical_url",
        "content_type",
        "title_or_summary",
        "cover_url",
        "author_platform_id",
        "author_name",
        "visible_like_count",
        "feed_position",
        "discovered_at",
        "raw_payload",
    ]
    total = len(candidates)
    rates = {}
    for field in fields:
        ok = sum(1 for candidate in candidates if getattr(candidate, field) not in (None, "", {}, []))
        rates[field] = {"count": ok, "rate": (ok / total if total else 0.0)}
    xsec_context_count = sum(1 for candidate in candidates if candidate.platform_context.get("has_xsec_context"))
    return {
        "target_count": target_count,
        "actual_count": total,
        "unique_candidate_count": len({candidate.platform_content_id for candidate in candidates}),
        "field_success": rates,
        "xhs_context_success": {
            "count": xsec_context_count,
            "rate": (xsec_context_count / total if total else 0.0),
        },
    }
