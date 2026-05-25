from datetime import datetime
import re
from typing import Any

from intelligence_engine.connectors.xhs.normalizer import parse_visible_count
from intelligence_engine.domain.schemas import CommentSnapshotInput
from intelligence_engine.filtering.candidate_classifier import LEAD_KEYWORDS, find_hits


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


def _parse_created_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp).astimezone()
        except OSError:
            return None
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{10,13}", text):
            return _parse_created_time(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def normalize_xhs_comment(raw: dict[str, Any], *, fallback_index: int = 0) -> CommentSnapshotInput | None:
    user = raw.get("user") or raw.get("userInfo") or raw.get("user_info") or {}
    target_comment = raw.get("target_comment") or raw.get("targetComment") or {}
    body_text = _first(raw.get("body_text"), raw.get("content"), raw.get("text"), raw.get("commentContent"))
    if isinstance(body_text, dict):
        body_text = _first(body_text.get("text"), body_text.get("content"))
    if not body_text:
        return None
    platform_comment_id = _first(
        raw.get("platform_comment_id"),
        raw.get("id"),
        raw.get("commentId"),
        raw.get("comment_id"),
        raw.get("cid"),
    )
    if not platform_comment_id:
        platform_comment_id = f"dom-comment-{fallback_index}-{abs(hash(body_text))}"
    return CommentSnapshotInput(
        platform_comment_id=str(platform_comment_id),
        parent_platform_comment_id=_first(raw.get("parent_comment_id"), raw.get("parentCommentId"), raw.get("parent_id"), target_comment.get("id")),
        author_platform_id=_first(raw.get("author_platform_id"), user.get("userId"), user.get("user_id"), user.get("id")),
        author_name=_first(raw.get("author_name"), user.get("nickname"), user.get("nickName"), user.get("name")),
        body_text=str(body_text).strip(),
        like_count=parse_visible_count(str(_first(raw.get("like_count"), raw.get("likeCount"), raw.get("likedCount"), raw.get("like_count_str")) or "")),
        created_time=_parse_created_time(_first(raw.get("created_time"), raw.get("createTime"), raw.get("create_time"), raw.get("time"))),
        raw_payload=raw,
    )


def normalize_xhs_comments(raw_payload: dict[str, Any], *, limit: int = 20) -> list[CommentSnapshotInput]:
    comments: list[CommentSnapshotInput] = []
    seen_ids: set[str] = set()
    raw_candidates: list[dict[str, Any]] = []

    for item in _deep_iter(raw_payload):
        keys = set(item.keys())
        if (
            {"content", "user"}.issubset(keys)
            or {"content", "userInfo"}.issubset(keys)
            or {"content", "user_info"}.issubset(keys)
            or {"commentId", "content"}.issubset(keys)
            or "body_text" in keys
        ):
            raw_candidates.append(item)

    for index, raw in enumerate(raw_candidates):
        comment = normalize_xhs_comment(raw, fallback_index=index)
        if not comment or comment.platform_comment_id in seen_ids:
            continue
        seen_ids.add(comment.platform_comment_id)
        comments.append(comment)
        if len(comments) >= limit:
            break
    return comments


def comment_field_report(comments: list[CommentSnapshotInput]) -> dict[str, Any]:
    fields = [
        "platform_comment_id",
        "parent_platform_comment_id",
        "author_platform_id",
        "author_name",
        "body_text",
        "like_count",
        "created_time",
        "raw_payload",
    ]
    total = len(comments)
    return {
        "total": total,
        "field_success": {
            field: {
                "count": sum(1 for comment in comments if getattr(comment, field) not in (None, "", {}, [])),
                "rate": (
                    sum(1 for comment in comments if getattr(comment, field) not in (None, "", {}, [])) / total
                    if total
                    else 0.0
                ),
            }
            for field in fields
        },
    }


def comment_keyword_hits(comments: list[CommentSnapshotInput]) -> list[str]:
    hits: list[str] = []
    for comment in comments:
        for hit in find_hits(comment.body_text, LEAD_KEYWORDS):
            if hit not in hits:
                hits.append(hit)
    return hits
