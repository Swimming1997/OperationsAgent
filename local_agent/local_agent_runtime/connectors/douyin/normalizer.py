"""Normalize Douyin ``aweme`` payloads into the unified content model.

Input is the JSON object Douyin's own web page fetches (captured via response
interception). Output matches the same ``FeedCandidateInput`` /
``DetailSnapshotInput`` / ``CommentSnapshotInput`` contracts used by XHS, so the
central intelligence pool stays platform-uniform.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterator

_JSON_DECODER = json.JSONDecoder()


def iter_stream_json(text: str) -> Iterator[dict[str, Any]]:
    """Yield top-level JSON objects from an app-framed JSON stream.

    Douyin's search endpoint returns a chunked/length-prefixed stream like
    ``17fe7\\n{...}\\n1a2b\\n{...}`` rather than one JSON document, so
    ``response.json()`` fails. We scan for ``{`` and decode objects greedily,
    skipping the hex length frames and whitespace in between.
    """

    if not text:
        return
    idx = 0
    n = len(text)
    while idx < n:
        if text[idx] != "{":
            idx += 1
            continue
        try:
            obj, end = _JSON_DECODER.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            yield obj
        idx = end

from local_agent_runtime.connectors.douyin.field import build_video_url
from local_agent_runtime.contracts import (
    CommentSnapshotInput,
    DetailSnapshotInput,
    FeedCandidateInput,
)
from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface


def extract_aweme_list(data: Any) -> list[dict[str, Any]]:
    """Pull aweme objects out of various Douyin web response shapes.

    Handles: ``{"aweme_list": [...]}`` (feed/user posts),
    ``{"data": [{"aweme_info": {...}}, ...]}`` (general search),
    ``{"data": [<aweme>, ...]}``, ``{"aweme_detail": {...}}`` (detail), and the
    jingxuan recommend feed which also carries items under ``chime_video_list``
    and ``preload_awemes``. Any object carrying an ``aweme_id`` is an aweme.
    """

    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []

    def _consume(obj: Any) -> None:
        if isinstance(obj, dict):
            if isinstance(obj.get("aweme_info"), dict):
                _consume(obj["aweme_info"])
                return
            if obj.get("aweme_id"):
                out.append(obj)

    detail = data.get("aweme_detail")
    if isinstance(detail, dict) and detail.get("aweme_id"):
        out.append(detail)

    for key in ("aweme_list", "data", "cards", "chime_video_list", "preload_awemes"):
        container = data.get(key)
        if isinstance(container, list):
            for item in container:
                _consume(item)
    return out


def unwrap_aweme_detail(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    detail = data.get("aweme_detail")
    if isinstance(detail, dict):
        return detail
    nested = data.get("data")
    if isinstance(nested, dict):
        detail = nested.get("aweme_detail") or nested.get("aweme")
        if isinstance(detail, dict):
            return detail
    items = extract_aweme_list(data)
    return items[0] if items else None


def normalize_douyin_suggestions(
    data: Any,
    *,
    core_keyword: str,
    fetched_at_iso: str,
) -> list[dict[str, Any]]:
    """Normalize a Douyin ``/search/sug/`` response into unified suggestion items.

    Output shape mirrors the XHS suggestion items so upper layers consume both
    platforms identically: ``core_keyword / suggested_keyword / suggestion_rank``.
    Rank follows ``word_record.words_position`` (0 = hottest) when present,
    otherwise the list order.
    """

    if not isinstance(data, dict):
        return []
    sug_list = data.get("sug_list")
    if not isinstance(sug_list, list):
        return []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for order, entry in enumerate(sug_list):
        if not isinstance(entry, dict):
            continue
        record = entry.get("word_record") if isinstance(entry.get("word_record"), dict) else {}
        keyword = str(entry.get("content") or record.get("words_content") or "").strip()
        if not keyword or keyword == core_keyword or keyword in seen:
            continue
        seen.add(keyword)
        position = record.get("words_position")
        try:
            rank = int(position) + 1 if position is not None else order + 1
        except (TypeError, ValueError):
            rank = order + 1
        items.append(
            {
                "core_keyword": core_keyword,
                "suggested_keyword": keyword,
                "suggestion_rank": rank,
                "raw_payload": {
                    "source": "search_sug_intercept",
                    "group_id": record.get("group_id"),
                    "words_position": position,
                    "words_source": record.get("words_source"),
                },
                "fetched_at": fetched_at_iso,
            }
        )
    items.sort(key=lambda item: item["suggestion_rank"])
    return items


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _epoch_to_dt(value: Any) -> datetime | None:
    seconds = _to_int(value)
    if not seconds or seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _first_url(url_container: Any) -> str | None:
    if isinstance(url_container, dict):
        url_list = url_container.get("url_list")
        if isinstance(url_list, list):
            for url in url_list:
                if isinstance(url, str) and url.strip():
                    return url.strip()
    return None


def _image_urls(aweme: dict[str, Any]) -> list[str]:
    images = aweme.get("images")
    urls: list[str] = []
    if isinstance(images, list):
        for image in images:
            url = _first_url(image)
            if url:
                urls.append(url)
    return urls


def _content_type(aweme: dict[str, Any]) -> ContentType:
    if _image_urls(aweme):
        return ContentType.IMAGE_TEXT
    if isinstance(aweme.get("video"), dict):
        return ContentType.VIDEO
    return ContentType.UNKNOWN


def normalize_douyin_aweme(
    aweme: dict[str, Any] | None,
    *,
    feed_position: int | None = None,
    discovered_at: datetime | None = None,
    source_surface: SourceSurface = SourceSurface.DOUYIN_VIDEO_HOME_FEED,
    feed_type: FeedType | None = FeedType.DOUYIN_VIDEO_HOME_FEED,
    search_keyword: str | None = None,
) -> FeedCandidateInput | None:
    if not isinstance(aweme, dict):
        return None
    aweme_id = str(aweme.get("aweme_id") or "").strip()
    if not aweme_id:
        return None
    author = aweme.get("author") if isinstance(aweme.get("author"), dict) else {}
    statistics = aweme.get("statistics") if isinstance(aweme.get("statistics"), dict) else {}
    video = aweme.get("video") if isinstance(aweme.get("video"), dict) else {}
    cover_url = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
    if not cover_url:
        image_urls = _image_urls(aweme)
        cover_url = image_urls[0] if image_urls else None

    raw_payload: dict[str, Any] = {"aweme_id": aweme_id}
    if search_keyword:
        raw_payload["search_keyword"] = search_keyword
        raw_payload["search_keywords"] = [search_keyword]

    sec_uid = str(author.get("sec_uid") or "").strip() or None
    platform_context: dict[str, Any] = {
        "aweme_id": aweme_id,
        "sec_uid": sec_uid,
        "api_detail_ready": True,  # detail fetchable by aweme_id alone
    }

    return FeedCandidateInput(
        platform=Platform.DOUYIN,
        platform_content_id=aweme_id,
        canonical_url=build_video_url(aweme_id),
        content_type=_content_type(aweme),
        title_or_summary=(str(aweme.get("desc") or "").strip() or None),
        cover_url=cover_url,
        author_platform_id=sec_uid or (str(author.get("uid") or "").strip() or None),
        author_name=(str(author.get("nickname") or "").strip() or None),
        visible_like_count=_to_int(statistics.get("digg_count")),
        source_surface=source_surface,
        feed_type=feed_type,
        feed_position=feed_position,
        discovered_at=discovered_at or datetime.now(timezone.utc),
        raw_payload=raw_payload,
        platform_context=platform_context,
    )


def normalize_douyin_detail(
    aweme: dict[str, Any] | None,
    *,
    platform_content_id: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> DetailSnapshotInput:
    aweme = aweme if isinstance(aweme, dict) else {}
    author = aweme.get("author") if isinstance(aweme.get("author"), dict) else {}
    statistics = aweme.get("statistics") if isinstance(aweme.get("statistics"), dict) else {}
    video = aweme.get("video") if isinstance(aweme.get("video"), dict) else {}
    return DetailSnapshotInput(
        title=(str(aweme.get("desc") or "").strip() or None),
        body_text=(str(aweme.get("desc") or "").strip() or None),
        author_platform_id=(str(author.get("sec_uid") or "").strip() or None),
        author_name=(str(author.get("nickname") or "").strip() or None),
        author_avatar_url=_first_url(author.get("avatar_thumb")),
        cover_url=_first_url(video.get("cover")) or _first_url(video.get("origin_cover")),
        image_urls=_image_urls(aweme),
        video_url=_first_url(video.get("play_addr")),
        like_count=_to_int(statistics.get("digg_count")),
        comment_count=_to_int(statistics.get("comment_count")),
        collect_count=_to_int(statistics.get("collect_count")),
        share_count=_to_int(statistics.get("share_count")),
        publish_time=_epoch_to_dt(aweme.get("create_time")),
        raw_payload={
            "aweme_id": str(aweme.get("aweme_id") or platform_content_id or ""),
            "diagnostics": diagnostics or {},
        },
    )


def normalize_douyin_comment(comment: dict[str, Any] | None) -> CommentSnapshotInput | None:
    if not isinstance(comment, dict):
        return None
    comment_id = str(comment.get("cid") or "").strip()
    body = str(comment.get("text") or "").strip()
    if not comment_id or not body:
        return None
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    return CommentSnapshotInput(
        platform_comment_id=comment_id,
        parent_platform_comment_id=(str(comment.get("reply_id") or "").strip() or None),
        author_platform_id=(str(user.get("sec_uid") or "").strip() or None),
        author_name=(str(user.get("nickname") or "").strip() or None),
        body_text=body,
        like_count=_to_int(comment.get("digg_count")),
        created_time=_epoch_to_dt(comment.get("create_time")),
        raw_payload={"cid": comment_id},
    )


def normalize_douyin_comments(data: Any, *, limit: int = 20) -> list[CommentSnapshotInput]:
    """Normalize comment-list response payloads captured from Douyin XHR."""

    payloads = data if isinstance(data, list) else [data]
    normalized: list[CommentSnapshotInput] = []
    seen: set[str] = set()
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        containers = [payload]
        if isinstance(payload.get("data"), dict):
            containers.append(payload["data"])
        for container in containers:
            comments = container.get("comments")
            if not isinstance(comments, list):
                continue
            for raw in comments:
                item = normalize_douyin_comment(raw)
                if item is None or item.platform_comment_id in seen:
                    continue
                normalized.append(item)
                seen.add(item.platform_comment_id)
                if len(normalized) >= limit:
                    return normalized
    return normalized


def normalize_douyin_creator_profile(user: dict[str, Any] | None) -> dict[str, Any]:
    user = user if isinstance(user, dict) else {}
    return {
        "creator_platform_id": str(user.get("sec_uid") or user.get("uid") or "").strip() or None,
        "creator_display_name": str(user.get("nickname") or "").strip() or None,
        "avatar_url": _first_url(user.get("avatar_thumb")) or _first_url(user.get("avatar_medium")),
        "signature": str(user.get("signature") or "").strip() or None,
        "follower_count": _to_int(user.get("follower_count")),
        "following_count": _to_int(user.get("following_count")),
        "total_favorited": _to_int(user.get("total_favorited")),
        "aweme_count": _to_int(user.get("aweme_count")),
        "ip_location": str(user.get("ip_location") or "").strip() or None,
        "verification": str(user.get("custom_verify") or user.get("enterprise_verify_reason") or "").strip() or None,
    }
