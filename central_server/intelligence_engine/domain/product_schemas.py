from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from intelligence_engine.domain.enums import (
    CandidateBucket,
    ContentWorkflowStatus,
    FeedType,
    NetworkEgressStrategy,
    Platform,
    ReferenceLibraryRating,
    ReferenceLibraryType,
    ReferenceLibraryUsageStatus,
    SourceSurface,
    TaskScheduleType,
    TaskTemplateType,
    UserRoleName,
    XhsLocationFilter,
    XhsNoteType,
    XhsPublishTime,
    XhsSearchScope,
    XhsSearchSort,
)
from intelligence_engine.domain.schemas import ApiModel


class UserCreateRequest(ApiModel):
    username: str
    display_name: str
    email: str | None = None
    password: str
    role_names: list[UserRoleName] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserUpdateRequest(ApiModel):
    display_name: str | None = None
    email: str | None = None
    status: str | None = None
    role_names: list[UserRoleName] | None = None


class UserPasswordResetRequest(ApiModel):
    password: str


class UserRead(ApiModel):
    id: str
    username: str
    display_name: str
    email: str | None = None
    status: str
    roles: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    employee_id: str | None = None


class RoleRead(ApiModel):
    id: str
    name: str
    description: str | None = None


class EmployeeCreateRequest(ApiModel):
    user_id: str | None = None
    display_name: str
    email: str | None = None
    status: str = "active"


class EmployeeRead(ApiModel):
    id: str
    user_id: str | None = None
    display_name: str
    email: str | None = None
    status: str


class EmployeeUpdateRequest(ApiModel):
    display_name: str | None = None
    email: str | None = None
    status: str | None = None
    user_id: str | None = None


class EmployeeWithUserCreateRequest(ApiModel):
    username: str
    display_name: str
    email: str | None = None
    password: str
    role: UserRoleName = UserRoleName.OPERATOR


class EmployeeListItem(EmployeeRead):
    user_username: str | None = None
    user_display_name: str | None = None
    account_count: int = 0
    agent_count: int = 0


class LocalAgentRead(ApiModel):
    id: str
    employee_id: str | None = None
    employee_display_name: str | None = None
    device_name: str | None = None
    machine_fingerprint: str | None = None
    status: str
    agent_version: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    last_heartbeat_at: datetime | None = None


class LocalAgentUpdateRequest(ApiModel):
    employee_id: str | None = None
    status: str | None = None


class BusinessAccountTypeCreateRequest(ApiModel):
    name: str
    description: str | None = None
    enabled: bool = True


class BusinessAccountTypeUpdateRequest(ApiModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class BusinessAccountTypeRead(ApiModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    rule_set_count: int = 0
    benchmark_group_count: int = 0


class PlatformAccountUpdateRequest(ApiModel):
    employee_id: str | None = None
    display_name: str | None = None
    external_account_id: str | None = None
    business_account_type_id: str | None = None
    status: str | None = None
    account_role: str | None = None
    health_status: str | None = None
    default_agent_id: str | None = None
    metadata: dict[str, Any] | None = None


class PlatformAccountCreateRequest(ApiModel):
    employee_id: str | None = None
    platform: Platform
    display_name: str
    external_account_id: str | None = None
    business_account_type: str | None = None
    business_account_type_id: str | None = None
    default_agent_id: str | None = None
    account_role: str = "intelligence_collector"
    health_status: str = "healthy"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountAgentBindingRead(ApiModel):
    id: str
    account_id: str
    agent_id: str
    employee_id: str | None = None
    agent_device_name: str | None = None
    agent_status: str | None = None
    enabled: bool
    session_status: str | None = None
    last_claimed_at: datetime | None = None


class AccountAgentBindingCreateRequest(ApiModel):
    agent_ids: list[str] = Field(default_factory=list)
    force: bool = False


class AccountAgentBindingRebindRequest(ApiModel):
    force: bool = False


class RegisterLocalAgentsRequest(ApiModel):
    agent_ids: list[str] = Field(default_factory=list)
    force: bool = False


class DiscoverLocalAgentItem(ApiModel):
    agent_id: str | None = None
    device_name: str | None = None
    machine_fingerprint: str | None = None
    bridge_port: int | None = None


class ResolveDiscoveredAgentsRequest(ApiModel):
    items: list[DiscoverLocalAgentItem] = Field(default_factory=list)


class ResolvedDiscoverMatch(ApiModel):
    agent: LocalAgentRead
    bridge_port: int | None = None


class PlatformAccountRead(ApiModel):
    id: str
    employee_id: str | None = None
    employee_display_name: str | None = None
    platform: str
    display_name: str
    external_account_id: str | None = None
    business_account_type_id: str | None = None
    business_account_type_name: str | None = None
    legacy_business_account_type: str | None = None
    status: str
    auth_status: str
    account_role: str = "intelligence_collector"
    health_status: str = "healthy"
    profile_key: str | None = None
    platform_nickname: str | None = None
    platform_home_url: str | None = None
    last_verified_at: datetime | None = None
    login_cdp_port: int | None = None
    default_agent_id: str | None = None
    bindings: list[AccountAgentBindingRead] = Field(default_factory=list)
    session_health_status: str | None = None
    active_login_session_status: str | None = None
    usage_status: str = "unavailable"
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkGroupCreateRequest(ApiModel):
    name: str
    description: str | None = None
    owner_employee_id: str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkGroupUpdateRequest(ApiModel):
    name: str | None = None
    description: str | None = None
    owner_employee_id: str | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class BenchmarkGroupRead(ApiModel):
    id: str
    name: str
    description: str | None = None
    owner_employee_id: str | None = None
    submitter_user_id: str | None = None
    submitter_employee_id: str | None = None
    submitter_name: str | None = None
    enabled: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkGroupMemberCreateRequest(ApiModel):
    creator_monitor_id: str | None = None
    platform: Platform
    creator_platform_id: str | None = None
    creator_profile_url: str | None = None
    display_name: str | None = None
    platform_context: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class BenchmarkGroupMemberUpdateRequest(ApiModel):
    platform: Platform | None = None
    creator_platform_id: str | None = None
    creator_profile_url: str | None = None
    display_name: str | None = None
    enabled: bool | None = None


class BenchmarkGroupMemberRead(ApiModel):
    id: str
    benchmark_group_id: str
    creator_monitor_id: str | None = None
    platform: str
    creator_platform_id: str | None = None
    creator_profile_url: str | None = None
    display_name: str | None = None
    platform_context: dict[str, Any] = Field(default_factory=dict)
    enabled: bool


class BindBenchmarkGroupRequest(ApiModel):
    business_account_type_id: str


class TaskTemplateCreateRequest(ApiModel):
    name: str
    template_type: TaskTemplateType
    platform: Platform | None = None
    account_id: str | None = None
    business_account_type_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class RecommendationFeedTaskPayload(ApiModel):
    executor_account_id: str
    feed_type: FeedType
    target_count: int = Field(default=50, ge=1, le=500)
    refresh_rounds: int = Field(default=2, ge=1, le=20)
    per_round_scroll_target: int = Field(default=50, ge=1, le=500)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class CreatorMonitorTaskPayload(ApiModel):
    executor_account_id: str
    benchmark_group_id: str
    auto_detail_fetch: bool = True
    max_latest_items: int = Field(default=20, ge=1, le=100)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class KeywordSearchTaskPayload(ApiModel):
    executor_account_id: str
    platform: Platform
    keywords: list[str] = Field(default_factory=list)
    keyword_group: str | None = None
    max_items: int = Field(default=50, ge=1, le=500)
    search_sort: XhsSearchSort = XhsSearchSort.COMPREHENSIVE
    note_type: XhsNoteType = XhsNoteType.ALL
    publish_time: XhsPublishTime = XhsPublishTime.ALL
    search_scope: XhsSearchScope = XhsSearchScope.ALL
    location_filter: XhsLocationFilter = XhsLocationFilter.ALL
    per_keyword_limit: int | None = Field(default=None, ge=1, le=500)
    collect_suggestions_first: bool = False
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None

    @model_validator(mode="after")
    def require_keywords_or_group(self):
        if not self.keywords and not self.keyword_group:
            raise ValueError("keywords or keyword_group is required")
        return self


class RecommendationFeedTemplateConfig(ApiModel):
    feed_type: FeedType
    target_count: int = Field(default=50, ge=1, le=500)
    refresh_rounds: int = Field(default=2, ge=1, le=20)
    per_round_scroll_target: int = Field(default=50, ge=1, le=500)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class CreatorMonitorTemplateConfig(ApiModel):
    benchmark_group_id: str
    auto_detail_fetch: bool = True
    max_latest_items: int = Field(default=20, ge=1, le=100)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class KeywordSearchTemplateConfig(ApiModel):
    platform: Platform
    keywords: list[str] = Field(default_factory=list)
    keyword_group: str | None = None
    max_items: int = Field(default=50, ge=1, le=500)
    search_sort: XhsSearchSort = XhsSearchSort.COMPREHENSIVE
    note_type: XhsNoteType = XhsNoteType.ALL
    publish_time: XhsPublishTime = XhsPublishTime.ALL
    search_scope: XhsSearchScope = XhsSearchScope.ALL
    location_filter: XhsLocationFilter = XhsLocationFilter.ALL
    per_keyword_limit: int | None = Field(default=None, ge=1, le=500)
    collect_suggestions_first: bool = False
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None

    @model_validator(mode="after")
    def require_keywords_or_group(self):
        if not self.keywords and not self.keyword_group:
            raise ValueError("keywords or keyword_group is required")
        return self


class RecommendationFeedTaskTemplateCreate(ApiModel):
    name: str
    business_account_type_id: str
    enabled: bool = True
    feed_type: FeedType
    target_count: int = Field(default=50, ge=1, le=500)
    refresh_rounds: int = Field(default=2, ge=1, le=20)
    per_round_scroll_target: int = Field(default=50, ge=1, le=500)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class RecommendationFeedTaskTemplateUpdate(ApiModel):
    name: str | None = None
    business_account_type_id: str | None = None
    enabled: bool | None = None
    feed_type: FeedType | None = None
    target_count: int | None = Field(default=None, ge=1, le=500)
    refresh_rounds: int | None = Field(default=None, ge=1, le=20)
    per_round_scroll_target: int | None = Field(default=None, ge=1, le=500)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class CreatorMonitorTaskTemplateCreate(ApiModel):
    name: str
    business_account_type_id: str
    enabled: bool = True
    benchmark_group_id: str
    auto_detail_fetch: bool = True
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class CreatorMonitorTaskTemplateUpdate(ApiModel):
    name: str | None = None
    business_account_type_id: str | None = None
    enabled: bool | None = None
    benchmark_group_id: str | None = None
    auto_detail_fetch: bool | None = None
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class KeywordSearchTaskTemplateCreate(ApiModel):
    name: str
    business_account_type_id: str
    enabled: bool = True
    platform: Platform
    keywords: list[str] = Field(default_factory=list)
    max_items: int = Field(default=50, ge=1, le=500)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None

    @model_validator(mode="after")
    def require_keywords(self):
        if not self.keywords:
            raise ValueError("keywords is required")
        return self


class KeywordSearchTaskTemplateUpdate(ApiModel):
    name: str | None = None
    business_account_type_id: str | None = None
    enabled: bool | None = None
    platform: Platform | None = None
    keywords: list[str] | None = None
    max_items: int | None = Field(default=None, ge=1, le=500)
    rule_set_id: str | None = None
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    risk_policy_id: str | None = None


class TaskTemplateRead(ApiModel):
    id: str
    name: str
    template_type: str
    platform: str | None = None
    account_id: str | None = None
    business_account_type_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    typed_payload: dict[str, Any] = Field(default_factory=dict)


class TaskTemplatePermissions(ApiModel):
    can_edit: bool
    can_run: bool
    can_schedule: bool
    can_delete: bool


class TaskTemplateListItem(ApiModel):
    id: str
    name: str
    template_type: str
    enabled: bool
    platform: str | None = None
    business_account_type_id: str | None = None
    business_account_type_name: str | None = None
    created_by_user_id: str | None = None
    created_by_display_name: str | None = None
    key_fields: dict[str, Any] = Field(default_factory=dict)
    permissions: TaskTemplatePermissions


class TaskTemplateRunRequest(ApiModel):
    executor_account_id: str


class TaskScheduleCreateRequest(ApiModel):
    task_template_id: str
    executor_account_id: str | None = None
    schedule_type: TaskScheduleType
    interval_seconds: int | None = None
    daily_time_window: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    next_run_at: datetime | None = None


class TaskScheduleUpdateRequest(ApiModel):
    executor_account_id: str | None = None
    schedule_type: TaskScheduleType | None = None
    interval_seconds: int | None = None
    daily_time_window: dict[str, Any] | None = None
    enabled: bool | None = None
    next_run_at: datetime | None = None


class TaskScheduleRead(ApiModel):
    id: str
    task_template_id: str
    executor_account_id: str | None = None
    created_by_user_id: str | None = None
    schedule_type: str
    interval_seconds: int | None = None
    daily_time_window: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_materialized_at: datetime | None = None


class ReadinessCheck(ApiModel):
    key: str
    ok: bool
    message: str


class TaskTemplateReadiness(ApiModel):
    ready: bool
    checks: list[ReadinessCheck] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class TaskRunJobRead(ApiModel):
    job_id: str
    job_type: str
    status: str
    account_id: str | None = None
    claimed_by_agent_id: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskRunQueueContext(ApiModel):
    waiting_reason: str
    message: str
    pending_jobs_ahead: int = 0
    job_priority: int | None = None
    agent_running_job_id: str | None = None
    agent_running_job_type: str | None = None
    agent_running_since: str | None = None


class TaskRunRead(ApiModel):
    id: str
    task_template_id: str | None = None
    trigger_type: str
    requested_by_user_id: str | None = None
    task_schedule_id: str | None = None
    status: str
    jobs_total: int
    jobs_pending: int
    jobs_running: int
    jobs_success: int
    jobs_failed: int
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_summary: dict[str, Any] = Field(default_factory=dict)
    jobs: list[TaskRunJobRead] = Field(default_factory=list)
    queue_context: TaskRunQueueContext | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


class TaskRunListResponse(ApiModel):
    items: list[TaskRunRead]


class TaskRunCreatedJob(ApiModel):
    job_id: str
    job_type: str
    status: str


class TaskRunResponse(ApiModel):
    task_run_id: str
    task_template_id: str | None = None
    jobs_created: int
    jobs: list[TaskRunCreatedJob]
    readiness: TaskTemplateReadiness


class BehaviorProfileCreateRequest(ApiModel):
    name: str
    description: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class BehaviorProfileRead(ApiModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)


class NetworkEgressProfileCreateRequest(ApiModel):
    name: str
    strategy: NetworkEgressStrategy = NetworkEgressStrategy.DIRECT_LOCAL
    description: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class NetworkEgressProfileRead(ApiModel):
    id: str
    name: str
    strategy: str
    description: str | None = None
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)


class RiskPolicyCreateRequest(ApiModel):
    name: str
    description: str | None = None
    enabled: bool = True
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class RiskPolicyRead(ApiModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    behavior_profile_id: str | None = None
    network_egress_profile_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ContentAssignRequest(ApiModel):
    assigned_to_user_id: str
    assigned_by_user_id: str | None = None
    remark: str | None = None


class ContentStatusActionRequest(ApiModel):
    user_id: str | None = None
    note: str | None = None


class ContentNoteCreateRequest(ApiModel):
    user_id: str | None = None
    note: str


class ContentWorkflowRead(ApiModel):
    content_id: str
    workflow_status: ContentWorkflowStatus
    assigned_to_user_id: str | None = None
    assigned_by_user_id: str | None = None
    assigned_at: datetime | None = None
    reviewed_at: datetime | None = None
    selected_at: datetime | None = None
    discarded_at: datetime | None = None
    latest_operator_note: str | None = None


class ContentBulkStatusRequest(ApiModel):
    content_ids: list[str] = Field(default_factory=list)
    action: str
    user_id: str | None = None
    note: str | None = None


class ContentBulkStatusFailure(ApiModel):
    content_id: str
    code: str
    message: str


class ContentBulkStatusResponse(ApiModel):
    succeeded: list[ContentWorkflowRead] = Field(default_factory=list)
    failed: list[ContentBulkStatusFailure] = Field(default_factory=list)


class ContentOperatorNoteRead(ApiModel):
    id: str
    content_id: str
    user_id: str | None = None
    note: str
    created_at: datetime


class IntelligenceContentProductItem(ApiModel):
    content_id: str
    platform: str
    platform_content_id: str
    content_type: str
    canonical_url: str | None = None
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    cover_display_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    collect_count: int | None = None
    candidate_bucket: str | None = None
    business_keyword_hits: list[str] = Field(default_factory=list)
    lead_keyword_hits: list[str] = Field(default_factory=list)
    comment_keyword_hits: list[str] = Field(default_factory=list)
    workflow_status: str
    assigned_to_user_id: str | None = None
    assigned_to_user_display_name: str | None = None
    latest_operator_note: str | None = None
    latest_snapshot_time: datetime | None = None
    latest_discovered_at: datetime | None = None
    discovery_sources_summary: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: datetime
    last_seen_at: datetime
    data_status: str = "card_only"
    discovery_count: int = 0
    discovered_account_count: int = 0
    discovered_search_keyword_count: int = 0
    platform_tags: list[str] = Field(default_factory=list)
    search_tags: list[str] = Field(default_factory=list)
    manual_tags: list[str] = Field(default_factory=list)
    search_keyword: str | None = None
    search_sort: str | None = None
    note_type_filter: str | None = None
    publish_time_filter: str | None = None
    search_scope_filter: str | None = None
    location_filter: str | None = None
    best_search_rank: int | None = None
    best_feed_position: int | None = None
    reference_library_count: int = 0
    in_reference_library: bool = False
    reference_library_type: str | None = None
    reference_library_rating: str | None = None
    reference_selection_sources: list[str] = Field(default_factory=list)
    reference_matched_keywords: list[str] = Field(default_factory=list)
    reference_ai_reason: str | None = None
    reference_manual_locked: bool = False


class IntelligenceContentProductList(ApiModel):
    items: list[IntelligenceContentProductItem]
    page: int
    page_size: int
    total: int


class BusinessAccountTypeRuleSetBindRequest(ApiModel):
    rule_set_id: str
    is_default: bool = False


class BusinessAccountTypeRuleSetRead(ApiModel):
    id: str
    business_account_type_id: str
    rule_set_id: str
    rule_set_name: str | None = None
    is_default: bool


class BenchmarkGroupBusinessAccountTypeRead(ApiModel):
    id: str
    benchmark_group_id: str
    business_account_type_id: str
    business_account_type_name: str | None = None


class BusinessAccountTypeBenchmarkGroupRead(ApiModel):
    id: str
    business_account_type_id: str
    benchmark_group_id: str
    benchmark_group_name: str | None = None


class KeywordRuleSetCreateRequest(ApiModel):
    name: str
    rule_scope: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class KeywordRuleSetUpdateRequest(ApiModel):
    name: str | None = None
    rule_scope: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class KeywordRuleSetRead(ApiModel):
    id: str
    name: str
    rule_scope: str
    enabled: bool
    created_by_user_id: str | None = None
    created_by_employee_id: str | None = None
    submitter_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class KeywordRuleCreateRequest(ApiModel):
    keyword: str
    normalized_keyword: str | None = None
    match_mode: str = "contains"
    enabled: bool = True
    weight: int = 1


class KeywordRuleUpdateRequest(ApiModel):
    keyword: str | None = None
    normalized_keyword: str | None = None
    match_mode: str | None = None
    enabled: bool | None = None
    weight: int | None = None


class KeywordRuleRead(ApiModel):
    id: str
    rule_set_id: str
    keyword: str
    normalized_keyword: str | None = None
    match_mode: str
    enabled: bool
    weight: int


class ProductOptions(ApiModel):
    roles: list[dict[str, str]]
    platforms: list[dict[str, str]]
    feed_types: list[dict[str, str]]
    task_template_types: list[dict[str, str]]
    workflow_statuses: list[dict[str, str]]
    candidate_buckets: list[dict[str, str]]
    account_statuses: list[dict[str, str]]
    agent_statuses: list[dict[str, str]]


class ContentIdentityDetail(ApiModel):
    id: str
    platform: str
    platform_content_id: str
    canonical_url: str | None = None
    content_type: str
    first_seen_at: datetime
    last_seen_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentSnapshotDetail(ApiModel):
    id: str
    title: str | None = None
    body_text: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    author_avatar_url: str | None = None
    cover_url: str | None = None
    cover_display_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_display_urls: list[str] = Field(default_factory=list)
    video_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    collect_count: int | None = None
    share_count: int | None = None
    publish_time: datetime | None = None
    fetched_at: datetime


class CommentSnapshotDetail(ApiModel):
    id: str
    platform_comment_id: str
    parent_platform_comment_id: str | None = None
    author_platform_id: str | None = None
    author_name: str | None = None
    body_text: str
    like_count: int | None = None
    created_time: datetime | None = None
    fetched_at: datetime


class CandidateDecisionDetail(ApiModel):
    id: str
    candidate_bucket: str
    business_keyword_hits: list[str] = Field(default_factory=list)
    lead_keyword_hits: list[str] = Field(default_factory=list)
    comment_keyword_hits: list[str] = Field(default_factory=list)
    decision_reason: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime


class AssignmentHistoryItem(ApiModel):
    id: str
    assigned_to_user_id: str
    assigned_by_user_id: str | None = None
    assigned_at: datetime
    status: str
    remark: str | None = None


class DiscoveryEventSummaryItem(ApiModel):
    id: str
    source_surface: str
    feed_type: str | None = None
    feed_position: int | None = None
    discovered_at: datetime
    account_id: str | None = None
    job_id: str | None = None
    search_keyword: str | None = None
    search_keywords: list[str] = Field(default_factory=list)


class IntelligenceContentProductDetail(ApiModel):
    identity: ContentIdentityDetail
    latest_snapshot: ContentSnapshotDetail | None = None
    comments: list[CommentSnapshotDetail] = Field(default_factory=list)
    latest_candidate_decision: CandidateDecisionDetail | None = None
    workflow_state: ContentWorkflowRead
    notes: list[ContentOperatorNoteRead] = Field(default_factory=list)
    assignment_history: list[AssignmentHistoryItem] = Field(default_factory=list)
    discovery_events_summary: list[DiscoveryEventSummaryItem] = Field(default_factory=list)
    reference_library_items: list["ReferenceLibraryItemRead"] = Field(default_factory=list)
    platform_tags: list[str] = Field(default_factory=list)
    search_tags: list[str] = Field(default_factory=list)
    manual_tags: list[str] = Field(default_factory=list)
    data_status: str = "card_only"
    pending_detail_job_id: str | None = None
    pending_comment_job_id: str | None = None


class ManualTagsUpdateRequest(ApiModel):
    tag_ids: list[str] = Field(default_factory=list)
    manual_tags: list[str] = Field(default_factory=list)
    user_id: str | None = None


class ManualTagCreateRequest(ApiModel):
    name: str


class ManualTagRead(ApiModel):
    id: str
    name: str
    status: str
    is_system: bool
    created_by_user_id: str | None = None
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    can_delete: bool = False


class ManualTagListResponse(ApiModel):
    items: list[ManualTagRead] = Field(default_factory=list)


class EnqueueFetchResponse(ApiModel):
    job_id: str
    job_type: str
    status: str


class XhsSearchSuggestionTaskRequest(ApiModel):
    executor_account_id: str
    core_keyword: str
    platform: Platform = Platform.XHS


class XhsSearchSuggestionRead(ApiModel):
    id: str
    platform: str
    core_keyword: str
    suggested_keyword: str
    suggestion_rank: int | None = None
    source_account_id: str | None = None
    fetched_at: datetime
    created_at: datetime


class ReferenceLibraryItemCreateRequest(ApiModel):
    library_type: ReferenceLibraryType
    selection_sources: list[str] = Field(default_factory=list)
    selected_reason: str | None = None
    rating: ReferenceLibraryRating | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    manual_tags: list[str] = Field(default_factory=list)
    material_tags: list[str] = Field(default_factory=list)
    usage_status: ReferenceLibraryUsageStatus = ReferenceLibraryUsageStatus.UNUSED
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
    employee_id: str | None = None


class ReferenceLibraryItemUpdateRequest(ApiModel):
    library_type: ReferenceLibraryType | None = None
    selection_sources: list[str] | None = None
    selected_reason: str | None = None
    rating: ReferenceLibraryRating | None = None
    matched_keywords: list[str] | None = None
    manual_tags: list[str] | None = None
    material_tags: list[str] | None = None
    usage_status: ReferenceLibraryUsageStatus | None = None
    note: str | None = None
    metadata: dict[str, Any] | None = None
    user_id: str | None = None
    employee_id: str | None = None


class CreativeMaterialPreparationRequest(ApiModel):
    reusable_angles: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    applicable_business_type_ids: list[str] = Field(default_factory=list)
    operator_note: str | None = None
    material_tags: list[str] | None = None


class ReferenceLibraryItemRead(ApiModel):
    id: str
    content_id: str
    platform: str | None = None
    library_type: str
    status: str
    created_by_user_id: str | None = None
    created_by_employee_id: str | None = None
    selected_reason: str | None = None
    rating: str | None = None
    selection_sources: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    selected_at: datetime | None = None
    manual_tags: list[str] = Field(default_factory=list)
    material_tags: list[str] = Field(default_factory=list)
    usage_status: str
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    cover_display_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    collect_count: int | None = None


class ReferenceLibraryItemList(ApiModel):
    items: list[ReferenceLibraryItemRead]
    page: int
    page_size: int
    total: int


class ReferenceLibraryEventRead(ApiModel):
    id: str
    library_item_id: str
    content_id: str
    event_type: str
    user_id: str | None = None
    employee_id: str | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ReferenceLibraryBulkCreateItem(ApiModel):
    content_id: str
    library_type: ReferenceLibraryType
    selection_sources: list[str] = Field(default_factory=list)
    selected_reason: str | None = None
    rating: ReferenceLibraryRating | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    manual_tags: list[str] = Field(default_factory=list)
    material_tags: list[str] = Field(default_factory=list)
    usage_status: ReferenceLibraryUsageStatus = ReferenceLibraryUsageStatus.UNUSED
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReferenceLibraryBulkCreateRequest(ApiModel):
    items: list[ReferenceLibraryBulkCreateItem] = Field(default_factory=list)


class ReferenceLibraryBulkCreateFailure(ApiModel):
    content_id: str
    code: str
    message: str


class ReferenceLibraryBulkCreateResponse(ApiModel):
    succeeded: list[ReferenceLibraryItemRead] = Field(default_factory=list)
    failed: list[ReferenceLibraryBulkCreateFailure] = Field(default_factory=list)


class ReferenceLibraryReevaluateRequest(ApiModel):
    content_ids: list[str] = Field(default_factory=list)
    item_ids: list[str] = Field(default_factory=list)
    trigger_source: str = "manual_re_evaluate"


class ReferenceLibraryReevaluateResult(ApiModel):
    content_id: str
    item_id: str | None = None
    status: str
    library_type: str | None = None
    rating: str | None = None
    reason: str | None = None


class ReferenceLibraryReevaluateResponse(ApiModel):
    results: list[ReferenceLibraryReevaluateResult]


class RuleProfileRead(ApiModel):
    id: str
    name: str
    platform: str
    library_type: str
    version: int
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class RuleProfileUpdateRequest(ApiModel):
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class OperationRuleRead(ApiModel):
    id: str
    rule_type: str
    title: str
    content: str
    platform: str | None = None
    enabled: bool
    version: int
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class OperationRuleCreateRequest(ApiModel):
    rule_type: str
    title: str
    content: str
    platform: str | None = None
    enabled: bool = True


class OperationRuleUpdateRequest(ApiModel):
    title: str | None = None
    content: str | None = None
    platform: str | None = None
    enabled: bool | None = None
    bump_version: bool = False


class IntelligenceDataQualityOverview(ApiModel):
    generated_at: str
    window_hours: int
    today_new_contents: int
    today_card_count: int
    today_detail_count: int
    today_comment_count: int
    today_reference_library_count: int
    detail_fetch_success_rate: float | None = None
    comment_fetch_success_rate: float | None = None
    search_context_completeness_rate: float
    platform_tags_coverage_rate: float
    multi_discovery_content_count: int
    abnormal_account_count: int
    runaway_detail_fetch_risk: bool
    filter_context_note: str
