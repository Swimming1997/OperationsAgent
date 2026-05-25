from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from local_agent_runtime.contracts import CommentSnapshotInput, DetailSnapshotInput, FeedCandidateInput
from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def map_homefeed_or_search_item(item: dict[str, Any], *, source_surface: SourceSurface) -> FeedCandidateInput:
    return FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id=str(item.get("platform_content_id") or ""),
        canonical_url=item.get("canonical_url"),
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary=item.get("title"),
        cover_url=item.get("cover_url"),
        author_name=item.get("author_name"),
        visible_like_count=item.get("visible_like_count"),
        source_surface=source_surface,
        feed_type=FeedType.XHS_HOME_FEED if source_surface == SourceSurface.XHS_HOME_FEED else None,
        feed_position=item.get("feed_position") or item.get("search_rank"),
        discovered_at=_parse_dt(item.get("discovered_at")),
        raw_payload=item.get("raw_payload") or item,
        platform_context={},
    )


def map_detail_payload(payload: dict[str, Any]) -> DetailSnapshotInput:
    publish_time = payload.get("publish_time")
    parsed_publish = None
    if isinstance(publish_time, str) and publish_time:
        try:
            parsed_publish = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
        except ValueError:
            parsed_publish = None
    return DetailSnapshotInput(
        title=payload.get("title"),
        body_text=payload.get("body_text"),
        author_name=payload.get("author_name"),
        image_urls=list(payload.get("image_urls") or []),
        like_count=payload.get("like_count"),
        comment_count=payload.get("comment_count"),
        collect_count=payload.get("collect_count"),
        publish_time=parsed_publish,
        raw_payload=payload.get("raw_payload") or {},
    )


def map_comment_item(item: dict[str, Any]) -> CommentSnapshotInput:
    created = item.get("comment_time")
    parsed_created = None
    if isinstance(created, str) and created:
        try:
            parsed_created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            parsed_created = None
    return CommentSnapshotInput(
        platform_comment_id=str(item.get("comment_id") or f"comment-{item.get('comment_rank')}"),
        author_name=item.get("comment_author"),
        body_text=str(item.get("comment_text") or ""),
        like_count=item.get("like_count"),
        created_time=parsed_created,
        raw_payload=item.get("raw_payload") or {},
    )


def validate_smoke_report(report: dict[str, Any]) -> dict[str, Any]:
    capability = report.get("capability")
    errors: list[str] = []
    mapped_count = 0

    if capability in {"homefeed", "search_collect"}:
        surface = SourceSurface.XHS_HOME_FEED if capability == "homefeed" else SourceSurface.SEARCH
        for index, item in enumerate(report.get("items") or [], start=1):
            try:
                mapped = map_homefeed_or_search_item(item, source_surface=surface)
                if not mapped.platform_content_id:
                    raise ValidationError.from_exception_data("FeedCandidateInput", [{"type": "missing", "loc": ("platform_content_id",), "msg": "required"}])
                mapped_count += 1
            except ValidationError as exc:
                errors.append(f"item[{index}]: {exc.errors()[0]['msg']}")
    elif capability == "detail":
        payload = report.get("payload") or ((report.get("items") or [{}])[0])
        try:
            map_detail_payload(payload)
            mapped_count = 1
        except ValidationError as exc:
            errors.append(f"detail: {exc.errors()[0]['msg']}")
    elif capability == "comments":
        for index, item in enumerate(report.get("items") or [], start=1):
            try:
                map_comment_item(item)
                mapped_count += 1
            except ValidationError as exc:
                errors.append(f"comment[{index}]: {exc.errors()[0]['msg']}")
    elif capability == "creator_notes":
        payload = report.get("payload") or {}
        for index, item in enumerate(payload.get("notes") or report.get("items") or [], start=1):
            try:
                map_homefeed_or_search_item(item, source_surface=SourceSurface.CREATOR_MONITOR)
                mapped_count += 1
            except ValidationError as exc:
                errors.append(f"note[{index}]: {exc.errors()[0]['msg']}")
    elif capability in {"login_check", "search_suggest"}:
        mapped_count = report.get("item_count") or 0
    else:
        errors.append(f"unsupported capability: {capability}")

    filter_status = report.get("filter_apply_status")
    requested = report.get("requested_filter_context") or {}
    applied = report.get("applied_filter_context")
    if filter_status == "applied" and applied is None:
        errors.append("filter_apply_status=applied but applied_filter_context is null")

    return {
        "valid": not errors,
        "capability": capability,
        "mapped_count": mapped_count,
        "errors": errors,
    }


def validate_smoke_json_file(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    result = validate_smoke_report(report)
    result["path"] = str(path)
    return result
