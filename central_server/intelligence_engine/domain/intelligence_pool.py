from __future__ import annotations

from typing import Any

from intelligence_engine.domain.enums import ContentDataStatus


def derive_data_status(
    *,
    latest_snapshot_id: str | None,
    comment_snapshot_count: int,
    detail_fetch_failed: bool = False,
    comment_fetch_failed: bool = False,
) -> str:
    if comment_fetch_failed and comment_snapshot_count == 0:
        return ContentDataStatus.COMMENTS_FAILED.value
    if detail_fetch_failed and not latest_snapshot_id:
        return ContentDataStatus.DETAIL_FAILED.value
    if comment_snapshot_count > 0:
        return ContentDataStatus.COMMENTS_READY.value
    if latest_snapshot_id:
        return ContentDataStatus.DETAIL_READY.value
    return ContentDataStatus.CARD_ONLY.value


def extract_platform_tags(*sources: dict[str, Any] | None) -> list[str]:
    tags: list[str] = []
    for source in sources:
        if not source:
            continue
        raw = source.get("platform_tags")
        if isinstance(raw, list):
            tags.extend(str(item) for item in raw if item)
    return list(dict.fromkeys(tags))


def extract_manual_tags(metadata: dict[str, Any] | None) -> list[str]:
    if not metadata:
        return []
    raw = metadata.get("manual_tags")
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return []


def extract_search_tags(metadata: dict[str, Any] | None, discovery_meta_rows: list[dict[str, Any]]) -> list[str]:
    tags: set[str] = set()
    if metadata:
        raw = metadata.get("search_tags")
        if isinstance(raw, list):
            tags.update(str(item) for item in raw if item)
    for meta in discovery_meta_rows:
        keyword = meta.get("search_keyword")
        if keyword:
            tags.add(str(keyword))
        core = meta.get("core_keyword")
        if core:
            tags.add(str(core))
    return sorted(tags)


def aggregate_search_context(discovery_meta_rows: list[dict[str, Any]]) -> dict[str, Any]:
    search_keyword: str | None = None
    search_sort: str | None = None
    note_type_filter: str | None = None
    publish_time_filter: str | None = None
    search_scope_filter: str | None = None
    location_filter: str | None = None
    best_search_rank: int | None = None
    best_feed_position: int | None = None
    discovered_search_keywords: set[str] = set()

    for meta in discovery_meta_rows:
        if not meta:
            continue
        keyword = meta.get("search_keyword")
        if keyword:
            discovered_search_keywords.add(str(keyword))
            search_keyword = search_keyword or str(keyword)
        if not search_sort and meta.get("search_sort"):
            search_sort = str(meta.get("search_sort"))
        note_type = meta.get("note_type") or meta.get("note_type_filter")
        if not note_type_filter and note_type:
            note_type_filter = str(note_type)
        publish_time = meta.get("publish_time") or meta.get("publish_time_filter")
        if not publish_time_filter and publish_time:
            publish_time_filter = str(publish_time)
        search_scope = meta.get("search_scope") or meta.get("search_scope_filter")
        if not search_scope_filter and search_scope:
            search_scope_filter = str(search_scope)
        if not location_filter and meta.get("location_filter"):
            location_filter = str(meta.get("location_filter"))
        rank = meta.get("search_rank")
        if isinstance(rank, int):
            best_search_rank = rank if best_search_rank is None else min(best_search_rank, rank)
        position = meta.get("feed_position")
        if isinstance(position, int):
            best_feed_position = position if best_feed_position is None else min(best_feed_position, position)

    return {
        "search_keyword": search_keyword,
        "search_sort": search_sort,
        "note_type_filter": note_type_filter,
        "publish_time_filter": publish_time_filter,
        "search_scope_filter": search_scope_filter,
        "location_filter": location_filter,
        "best_search_rank": best_search_rank,
        "best_feed_position": best_feed_position,
        "discovered_search_keyword_count": len(discovered_search_keywords),
    }


def build_discovery_meta_from_candidate(raw_payload: dict[str, Any] | None, *, feed_position: int | None = None) -> dict[str, Any]:
    payload = dict(raw_payload or {})
    meta = {
        "raw_payload": payload,
        "search_keyword": payload.get("search_keyword"),
        "search_keywords": payload.get("search_keywords"),
        "core_keyword": payload.get("core_keyword"),
        "suggested_keyword_rank": payload.get("suggested_keyword_rank"),
        "search_sort": payload.get("search_sort"),
        "note_type": payload.get("note_type") or payload.get("note_type_filter"),
        "publish_time": payload.get("publish_time") or payload.get("publish_time_filter"),
        "search_scope": payload.get("search_scope") or payload.get("search_scope_filter"),
        "location_filter": payload.get("location_filter"),
        "search_rank": payload.get("search_rank"),
        "feed_position": payload.get("feed_position") if payload.get("feed_position") is not None else feed_position,
        "requested_filter_context": payload.get("requested_filter_context"),
        "applied_filter_context": payload.get("applied_filter_context"),
        "filter_apply_status": payload.get("filter_apply_status"),
    }
    return {key: value for key, value in meta.items() if value is not None}
