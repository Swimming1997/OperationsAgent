from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from local_agent_runtime.enums import ContentType, FeedType, Platform, SourceSurface


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class FeedCandidateInput(ApiModel):
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
    platform_context: dict[str, Any] = Field(default_factory=dict)


class FeedCandidateIngestionRequest(ApiModel):
    job_id: str
    account_id: str | None = None
    candidates: list[FeedCandidateInput]


class DetailSnapshotInput(ApiModel):
    title: str | None = None
    body_text: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    author_avatar_url: str | None = None
    cover_url: str | None = None
    cover_image_base64: str | None = None
    cover_content_type: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    video_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    collect_count: int | None = None
    share_count: int | None = None
    publish_time: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class DetailIngestionRequest(ApiModel):
    job_id: str
    content_id: str
    snapshot: DetailSnapshotInput


class CommentSnapshotInput(ApiModel):
    platform_comment_id: str
    parent_platform_comment_id: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    body_text: str
    like_count: int | None = None
    created_time: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CommentIngestionRequest(ApiModel):
    job_id: str
    content_id: str
    comments: list[CommentSnapshotInput]


class CreatorMonitorIngestionRequest(ApiModel):
    job_id: str
    account_id: str | None = None
    creator_monitor_id: str
    creator_display_name: str | None = None
    items: list[FeedCandidateInput]
    raw_payload: dict[str, Any] = Field(default_factory=dict)

