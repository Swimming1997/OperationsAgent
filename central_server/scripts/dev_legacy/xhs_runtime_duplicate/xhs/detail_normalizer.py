from datetime import datetime
import re
from typing import Any

from intelligence_engine.connectors.xhs.normalizer import parse_visible_count
from intelligence_engine.domain.schemas import DetailSnapshotInput


def _deep_iter(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _deep_iter(child)
    elif isinstance(value, list):
        for child in value:
            yield from _deep_iter(child)


def _first(*values):
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_publish_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp).astimezone()
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{10,13}", text):
            return _parse_publish_time(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _collect_image_urls(note: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for image in note.get("imageList") or note.get("images") or note.get("image_list") or []:
        if isinstance(image, str):
            urls.append(image)
        elif isinstance(image, dict):
            url = _first(
                image.get("url"),
                image.get("url_default"),
                image.get("traceId"),
                image.get("src"),
                image.get("original"),
                (image.get("infoList") or [{}])[0].get("url") if isinstance(image.get("infoList"), list) else None,
                (image.get("info_list") or [{}])[0].get("url") if isinstance(image.get("info_list"), list) else None,
            )
            if url:
                urls.append(url)
    return list(dict.fromkeys(urls))


def _find_note_payload(raw_payload: dict[str, Any], platform_content_id: str | None = None) -> dict[str, Any]:
    best: dict[str, Any] = {}
    best_score = 0
    for item in _deep_iter(raw_payload):
        if platform_content_id and platform_content_id not in str(item):
            continue
        score = 0
        for key in ("title", "desc", "noteId", "note_id", "interactInfo", "user", "imageList", "video"):
            if key in item:
                score += 1
        if score > best_score:
            best_score = score
            best = item
    if best:
        return best
    for item in _deep_iter(raw_payload):
        if "title" in item or "desc" in item:
            return item
    return {}


def normalize_xhs_detail_payload(
    raw_payload: dict[str, Any],
    *,
    platform_content_id: str | None = None,
    dom_fallback: dict[str, Any] | None = None,
) -> DetailSnapshotInput:
    dom_fallback = dom_fallback or {}
    note = _find_note_payload(raw_payload, platform_content_id)
    interact = note.get("interactInfo") or note.get("interact_info") or {}
    user = note.get("user") or note.get("userInfo") or note.get("user_info") or {}
    video = note.get("video") or note.get("videoInfo") or {}
    image_urls = _collect_image_urls(note) or dom_fallback.get("image_urls") or []
    cover_url = _first(note.get("cover"), note.get("coverUrl"), note.get("cover_url"), dom_fallback.get("cover_url"), image_urls[0] if image_urls else None)
    if isinstance(cover_url, dict):
        cover_url = _first(cover_url.get("url"), cover_url.get("src"))
    video_url = _first(video.get("url"), video.get("masterUrl"), video.get("videoUrl"), dom_fallback.get("video_url"))
    if isinstance(video_url, dict):
        video_url = _first(video_url.get("url"), video_url.get("masterUrl"))

    return DetailSnapshotInput(
        title=_first(note.get("title"), dom_fallback.get("title")),
        body_text=_first(note.get("desc"), note.get("description"), note.get("content"), dom_fallback.get("body_text")),
        author_platform_id=_first(user.get("userId"), user.get("user_id"), user.get("id"), note.get("userId"), note.get("user_id"), dom_fallback.get("author_platform_id")),
        author_name=_first(user.get("nickname"), user.get("nickName"), user.get("name"), dom_fallback.get("author_name")),
        author_avatar_url=_first(user.get("avatar"), user.get("image"), user.get("avatarUrl"), dom_fallback.get("author_avatar_url")),
        like_count=parse_visible_count(str(_first(interact.get("likedCount"), interact.get("likeCount"), interact.get("liked_count"), interact.get("like_count"), dom_fallback.get("like_count")) or "")),
        comment_count=parse_visible_count(str(_first(interact.get("commentCount"), interact.get("comment_count"), dom_fallback.get("comment_count")) or "")),
        collect_count=parse_visible_count(str(_first(interact.get("collectedCount"), interact.get("collectCount"), interact.get("collected_count"), interact.get("collect_count"), dom_fallback.get("collect_count")) or "")),
        share_count=parse_visible_count(str(_first(interact.get("shareCount"), interact.get("share_count"), dom_fallback.get("share_count")) or "")),
        publish_time=_parse_publish_time(_first(note.get("time"), note.get("publishTime"), note.get("publish_time"), note.get("create_time"), dom_fallback.get("publish_time"))),
        cover_url=cover_url,
        image_urls=image_urls,
        video_url=video_url,
        raw_payload={"json_payload": raw_payload, "dom_fallback": dom_fallback},
    )


def detail_field_report(snapshots: list[DetailSnapshotInput]) -> dict[str, Any]:
    fields = [
        "title",
        "body_text",
        "author_platform_id",
        "author_name",
        "author_avatar_url",
        "like_count",
        "comment_count",
        "collect_count",
        "share_count",
        "publish_time",
        "cover_url",
        "image_urls",
        "video_url",
        "raw_payload",
    ]
    total = len(snapshots)
    return {
        "total": total,
        "field_success": {
            field: {
                "count": sum(1 for snapshot in snapshots if getattr(snapshot, field) not in (None, "", [], {})),
                "rate": (
                    sum(1 for snapshot in snapshots if getattr(snapshot, field) not in (None, "", [], {})) / total
                    if total
                    else 0.0
                ),
            }
            for field in fields
        },
    }
