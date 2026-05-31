from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intelligence_engine.domain.enums import (
    AccountStatus,
    AgentStatus,
    CandidateBucket,
    ContentType,
    ErrorCode,
    FeedType,
    JobStatus,
    JobType,
    Platform,
    SourceSurface,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ErrorPayload(ApiModel):
    code: ErrorCode
    message: str
    retryable: bool = False
    raw_context: dict[str, Any] = Field(default_factory=dict)


class AgentRegisterRequest(ApiModel):
    agent_id: str | None = None
    employee_id: str | None = None
    device_name: str | None = None
    machine_fingerprint: str | None = None
    agent_version: str | None = "0.1.0"
    capabilities: dict[str, Any] = Field(default_factory=dict)


class AgentRegisterResponse(ApiModel):
    agent_id: str
    status: AgentStatus


class AgentHeartbeatRequest(ApiModel):
    status: AgentStatus = AgentStatus.ONLINE
    agent_version: str | None = None
    running_job_ids: list[str] = Field(default_factory=list)
    session_health: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] | None = None


class AccountCreateRequest(ApiModel):
    employee_id: str | None = None
    platform: Platform
    display_name: str
    external_account_id: str | None = None
    business_account_type: str | None = None
    business_account_type_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountCreateResponse(ApiModel):
    account_id: str
    status: AccountStatus


class AccountSessionCreateRequest(ApiModel):
    local_agent_id: str
    session_type: str
    profile_ref: str | None = None
    cookie_ref: str | None = None
    status: str = "ready"
    session_meta: dict[str, Any] = Field(default_factory=dict)


class AccountSessionRead(ApiModel):
    session_id: str
    account_id: str
    local_agent_id: str
    platform: Platform
    session_type: str
    status: str
    session_meta: dict[str, Any] = Field(default_factory=dict)


class FeedCollectCreateRequest(ApiModel):
    account_id: str
    feed_type: FeedType
    target_count: int = 50
    refresh_rounds: int = 2
    per_round_scroll_target: int = 50
    priority: int = 100


class CreatorMonitorJobCreateRequest(ApiModel):
    creator_monitor_id: str
    priority: int = 100


class JobCreateResponse(ApiModel):
    job_id: str
    status: JobStatus


class JobRead(ApiModel):
    id: str
    job_type: JobType
    status: JobStatus
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    result_summary: dict[str, Any]
    retry_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None


class ClaimJobsRequest(ApiModel):
    max_jobs: int = 1
    supported_job_types: list[JobType] = Field(default_factory=list)


class ClaimedJob(ApiModel):
    job_id: str
    job_type: JobType
    account_id: str | None = None
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    claim_expires_at: datetime


class ClaimJobsResponse(ApiModel):
    jobs: list[ClaimedJob]


class JobStartRequest(ApiModel):
    agent_id: str


class JobProgressRequest(ApiModel):
    agent_id: str
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    partial_metrics: dict[str, Any] = Field(default_factory=dict)


class JobCompleteRequest(ApiModel):
    agent_id: str
    status: JobStatus = JobStatus.SUCCESS
    result_summary: dict[str, Any] = Field(default_factory=dict)


class JobFailRequest(ApiModel):
    agent_id: str
    error: ErrorPayload
    checkpoint: dict[str, Any] = Field(default_factory=dict)


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


class FeedCandidateIngestionResult(ApiModel):
    platform_content_id: str
    content_id: str
    is_new_content: bool
    detail_job_enqueued: bool
    discovery_event_id: str
    feed_prelim_pass: bool | None = None


class FeedCandidateIngestionResponse(ApiModel):
    results: list[FeedCandidateIngestionResult]


class CreatorMonitorIngestionRequest(ApiModel):
    job_id: str
    account_id: str | None = None
    creator_monitor_id: str
    creator_display_name: str | None = None
    items: list[FeedCandidateInput]
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CreatorMonitorIngestionResponse(ApiModel):
    items_seen: int
    new_content_count: int
    duplicate_content_count: int
    detail_job_enqueue_count: int
    creator_event_count: int


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


class DetailIngestionResponse(ApiModel):
    snapshot_id: str
    candidate_decision_enqueued: bool
    comment_job_enqueued: bool


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


class CommentIngestionResponse(ApiModel):
    inserted: int
    updated: int
    lead_keyword_hits: list[str]


class CreatorMonitorCreateRequest(ApiModel):
    platform: Platform
    creator_platform_id: str
    creator_display_name: str | None = None
    monitor_group_key: str | None = None
    mapped_business_account_type: str | None = None
    check_interval_seconds: int = 900


class CreatorMonitorCreateResponse(ApiModel):
    creator_monitor_id: str


class IntelligenceContentItem(ApiModel):
    content_id: str
    platform: Platform
    content_type: ContentType
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    candidate_bucket: CandidateBucket | None = None
    latest_discovered_at: datetime | None = None


class IntelligenceContentList(ApiModel):
    items: list[IntelligenceContentItem]
    page: int
    page_size: int
    total: int
