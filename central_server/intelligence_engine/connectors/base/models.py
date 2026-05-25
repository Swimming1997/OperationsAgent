from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from intelligence_engine.domain.enums import ContentType, FeedType, Platform, SourceSurface


class FeedCandidate(BaseModel):
    platform: Platform
    platform_content_id: str
    canonical_url: str | None = None
    content_type: ContentType = ContentType.UNKNOWN
    title_or_summary: str | None = None
    cover_url: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    visible_like_count: int | None = None
    source_surface: SourceSurface
    feed_type: FeedType | None = None
    feed_position: int | None = None
    discovered_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class DetailSnapshot(BaseModel):
    title: str | None = None
    body_text: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    video_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    collect_count: int | None = None
    share_count: int | None = None
    publish_time: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CommentSnapshot(BaseModel):
    platform_comment_id: str
    parent_platform_comment_id: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    body_text: str
    like_count: int | None = None
    created_time: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
