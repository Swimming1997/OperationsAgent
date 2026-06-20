from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.connectors.xhs.context import build_xhs_note_url, context_from_url_and_raw, enrich_xhs_platform_context, normalize_xhs_url

CONTENT_ID_PATTERNS = [
    re.compile(r"/explore/([0-9a-zA-Z]+)"),
    re.compile(r"/discovery/item/([0-9a-zA-Z]+)"),
]


def sanitize_feed_author_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_visible_count(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
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
    text = " ".join(
        str(raw.get(key) or "")
        for key in ["href", "card_class", "card_text", "cover_url", "model_type"]
    ).lower()
    if "video" in text or "视频" in text:
        return ContentType.VIDEO
    return ContentType.IMAGE_TEXT


def build_search_filter_context(
    *,
    search_sort: str | None = None,
    note_type: str | None = None,
    publish_time: str | None = None,
    search_scope: str | None = None,
    location_filter: str | None = None,
) -> dict[str, Any]:
    return {
        "search_sort": search_sort or "comprehensive",
        "note_type": note_type or "all",
        "publish_time": publish_time or "all",
        "search_scope": search_scope or "all",
        "location_filter": location_filter or "all",
    }


def normalize_xhs_search_card(
    raw: dict[str, Any],
    *,
    search_keyword: str,
    rank_position: int,
    discovered_at: datetime | None = None,
    search_sort: str | None = None,
    note_type: str | None = None,
    publish_time: str | None = None,
    search_scope: str | None = None,
    location_filter: str | None = None,
) -> FeedCandidateInput | None:
    candidate = normalize_xhs_card(raw, feed_position=rank_position, discovered_at=discovered_at)
    if not candidate:
        return None
    context = dict(candidate.platform_context or {})
    if not context.get("xsec_source"):
        context = enrich_xhs_platform_context(context, source_surface=SourceSurface.SEARCH.value)
    payload = dict(candidate.raw_payload or {})
    requested_filter_context = build_search_filter_context(
        search_sort=search_sort,
        note_type=note_type,
        publish_time=publish_time,
        search_scope=search_scope,
        location_filter=location_filter,
    )
    payload.update(
        {
            "search_keyword": search_keyword,
            "search_keywords": [search_keyword],
            "search_rank": rank_position,
            "search_sort": search_sort,
            "note_type": note_type,
            "publish_time": publish_time,
            "search_scope": search_scope,
            "location_filter": location_filter,
            "rank_position": rank_position,
            "requested_filter_context": requested_filter_context,
            "applied_filter_context": None,
            "filter_apply_status": "not_implemented",
        }
    )
    return candidate.model_copy(
        update={
            "source_surface": SourceSurface.SEARCH,
            "feed_type": None,
            "feed_position": rank_position,
            "platform_context": context,
            "canonical_url": build_xhs_note_url(context, fallback_url=candidate.canonical_url, source_surface=SourceSurface.SEARCH.value)
            or candidate.canonical_url,
            "raw_payload": payload,
        }
    )


def normalize_xhs_card(raw: dict[str, Any], *, feed_position: int, discovered_at: datetime | None = None) -> FeedCandidateInput | None:
    href = raw.get("href") or raw.get("canonical_url")
    canonical_url = normalize_xhs_url(href)
    platform_context = context_from_url_and_raw(
        canonical_url,
        raw,
        source_surface=SourceSurface.XHS_HOME_FEED.value,
    )
    platform_context = enrich_xhs_platform_context(platform_context, source_surface=SourceSurface.XHS_HOME_FEED.value)
    canonical_url = build_xhs_note_url(
        platform_context,
        fallback_url=canonical_url,
        source_surface=SourceSurface.XHS_HOME_FEED.value,
    ) or canonical_url
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
    xsec_context_count = sum(1 for candidate in candidates if (candidate.platform_context or {}).get("api_detail_ready"))
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


def coverage_from_field_report(report: dict[str, Any], fields: list[str]) -> dict[str, float]:
    field_success = report.get("field_success") or {}
    return {field: float((field_success.get(field) or {}).get("rate", 0.0)) for field in fields}


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def extract_xhs_card_image_urls(raw: dict[str, Any]) -> list[str]:
    note = raw.get("note_card") or raw.get("note") or raw.get("card") or raw
    if not isinstance(note, dict):
        return []
    urls: list[str] = []
    for image in note.get("image_list") or note.get("imageList") or note.get("images") or []:
        if isinstance(image, str):
            candidates = [image]
        elif isinstance(image, dict):
            candidates = [
                image.get("url_default"),
                image.get("url"),
                image.get("src"),
                *[
                    info.get("url")
                    for info in (image.get("info_list") or image.get("infoList") or [])
                    if isinstance(info, dict)
                ],
            ]
        else:
            continue
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value and value not in urls:
                urls.append(value)
                break
    return urls


def iter_xhs_api_cards(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    raw_items = _pick_first(
        data.get("items"),
        data.get("feeds"),
        data.get("notes"),
        (data.get("result") or {}).get("items") if isinstance(data.get("result"), dict) else None,
    )
    if not isinstance(raw_items, list):
        return []
    cards: list[dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        model_type = str(raw.get("model_type") or "").lower()
        if model_type and model_type != "note":
            continue
        note = raw.get("note_card") or raw.get("note") or raw.get("card") or raw
        if not isinstance(note, dict):
            continue
        user = note.get("user") or note.get("user_info") or raw.get("user") or {}
        interact = note.get("interact_info") or note.get("interactInfo") or {}
        cover = note.get("cover") or {}
        note_id = _pick_first(raw.get("id"), raw.get("note_id"), note.get("id"), note.get("note_id"))
        if not note_id:
            continue
        xsec_token = _pick_first(raw.get("xsec_token"), note.get("xsec_token"))
        xsec_source = _pick_first(raw.get("xsec_source"), note.get("xsec_source"))
        href = build_xhs_note_url(
            {
                "note_id": str(note_id),
                "xsec_token": str(xsec_token or ""),
                "xsec_source": str(xsec_source or ""),
            },
            source_surface="search_api" if xsec_source == "pc_search" else "homefeed_api",
        )
        cards.append(
            {
                "href": href,
                "platform_content_id": str(note_id),
                "title": _pick_first(note.get("display_title"), note.get("title"), note.get("desc")),
                "cover_url": _pick_first(
                    cover.get("url_default") if isinstance(cover, dict) else None,
                    cover.get("url_pre") if isinstance(cover, dict) else None,
                    note.get("cover_url"),
                ),
                "author_name": _pick_first(
                    user.get("nickname") if isinstance(user, dict) else None,
                    user.get("nick_name") if isinstance(user, dict) else None,
                    user.get("name") if isinstance(user, dict) else None,
                ),
                "author_platform_id": _pick_first(
                    user.get("user_id") if isinstance(user, dict) else None,
                    user.get("userId") if isinstance(user, dict) else None,
                    user.get("id") if isinstance(user, dict) else None,
                ),
                "visible_like_count": _pick_first(
                    interact.get("liked_count") if isinstance(interact, dict) else None,
                    interact.get("likedCount") if isinstance(interact, dict) else None,
                    note.get("liked_count"),
                ),
                "image_urls": extract_xhs_card_image_urls(raw),
                "xsec_token": xsec_token,
                "xsec_source": xsec_source,
                "model_type": raw.get("model_type") or note.get("model_type"),
                "api_raw": raw,
            }
        )
    return cards


def normalize_search_api_items(data: dict[str, Any] | None, *, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(data.get("items") or [], start=1):
        if len(items) >= limit:
            break
        note = raw.get("note_card") or raw.get("note") or raw
        note_id = _pick_first(raw.get("id"), note.get("id"), note.get("note_id"))
        xsec_token = _pick_first(raw.get("xsec_token"), note.get("xsec_token"))
        xsec_source = _pick_first(raw.get("xsec_source"), note.get("xsec_source"))
        context = enrich_xhs_platform_context(
            {
                "note_id": str(note_id or ""),
                "xsec_token": str(xsec_token or ""),
                "xsec_source": str(xsec_source or ""),
            },
            source_surface="search_api",
        )
        title = _pick_first(note.get("display_title"), note.get("title"), note.get("desc"))
        user = note.get("user") or note.get("user_info") or {}
        items.append(
            {
                "index": len(items) + 1,
                "keyword": keyword,
                "platform_content_id": str(note_id or ""),
                "title_or_summary": title,
                "author_name": _pick_first(user.get("nickname"), user.get("nick_name"), user.get("name")),
                "author_platform_id": _pick_first(user.get("user_id"), user.get("userId"), user.get("id")),
                "xsec_token": context.get("xsec_token") or None,
                "xsec_source": context.get("xsec_source") or None,
                "xsec_source_effective": context.get("xsec_source_effective"),
                "xsec_source_status": context.get("xsec_source_status"),
                "model_type": raw.get("model_type") or note.get("model_type"),
                "has_note_id": context.get("has_note_id"),
                "has_xsec_token": context.get("has_xsec_token"),
                "has_xsec_source": context.get("has_xsec_source"),
                "api_detail_ready": context.get("api_detail_ready"),
                "canonical_url": build_xhs_note_url(context, source_surface="search_api"),
                "raw_payload_preview": {
                    "id": note_id,
                    "xsec_token": xsec_token,
                    "xsec_source": xsec_source,
                    "model_type": raw.get("model_type") or note.get("model_type"),
                },
            }
        )
    return items


def search_api_field_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    def count(field: str) -> int:
        return sum(1 for item in items if item.get(field))
    return {
        "items_count": total,
        "items_with_id": count("platform_content_id"),
        "items_with_xsec_token": count("xsec_token"),
        "items_with_xsec_source": sum(1 for item in items if item.get("xsec_source")),
        "detail_ready_count": count("api_detail_ready"),
    }
