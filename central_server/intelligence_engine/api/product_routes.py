from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.db.models import (
    AccountAgentBinding,
    AccountSession,
    BenchmarkGroup,
    BenchmarkGroupMember,
    BusinessAccountType,
    BusinessAccountTypeBenchmarkGroup,
    BusinessAccountTypeRuleSet,
    Employee,
    CandidateDecision,
    CommentSnapshot,
    ContentIdentity,
    ContentSnapshot,
    KeywordRuleSet,
    KeywordRule,
    LocalAgent,
    Job,
    OperationRule,
    PlatformAccount,
    RuleProfile,
    TaskRun,
    TaskSchedule,
    TaskTemplate,
    User,
    XhsSearchSuggestion,
)
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import (
    AccountRole,
    AccountStatus,
    AgentStatus,
    AuthStatus,
    ContentDataStatus,
    JobStatus,
    JobType,
    Platform,
    OperationRuleType,
    UserRoleName,
)
from intelligence_engine.domain.product_schemas import (
    AccountAgentBindingCreateRequest,
    AccountAgentBindingRead,
    AccountAgentBindingRebindRequest,
    RegisterLocalAgentsRequest,
    ResolveDiscoveredAgentsRequest,
    ResolvedDiscoverMatch,
    AssignmentHistoryItem,
    BehaviorProfileCreateRequest,
    BehaviorProfileRead,
    BenchmarkGroupCreateRequest,
    BenchmarkGroupBusinessAccountTypeRead,
    BenchmarkGroupMemberCreateRequest,
    BenchmarkGroupMemberRead,
    BenchmarkGroupMemberUpdateRequest,
    BenchmarkGroupRead,
    BenchmarkGroupUpdateRequest,
    BindBenchmarkGroupRequest,
    BusinessAccountTypeCreateRequest,
    BusinessAccountTypeRead,
    BusinessAccountTypeUpdateRequest,
    BusinessAccountTypeRuleSetBindRequest,
    BusinessAccountTypeBenchmarkGroupRead,
    BusinessAccountTypeRuleSetRead,
    ContentAssignRequest,
    ContentBulkStatusFailure,
    ContentBulkStatusRequest,
    ContentBulkStatusResponse,
    CandidateDecisionDetail,
    CommentSnapshotDetail,
    ContentIdentityDetail,
    ContentSnapshotDetail,
    ContentNoteCreateRequest,
    ContentOperatorNoteRead,
    ContentStatusActionRequest,
    ContentWorkflowRead,
    CreatorMonitorTaskTemplateCreate,
    CreatorMonitorTaskTemplateUpdate,
    DiscoveryEventSummaryItem,
    EnqueueFetchResponse,
    EmployeeCreateRequest,
    EmployeeListItem,
    EmployeeRead,
    EmployeeUpdateRequest,
    EmployeeWithUserCreateRequest,
    IntelligenceContentProductDetail,
    IntelligenceContentProductList,
    IntelligenceDataQualityOverview,
    KeywordRuleCreateRequest,
    KeywordRuleRead,
    KeywordRuleSetCreateRequest,
    KeywordRuleSetRead,
    KeywordRuleSetUpdateRequest,
    KeywordRuleUpdateRequest,
    KeywordSearchTaskTemplateCreate,
    KeywordSearchTaskTemplateUpdate,
    LocalAgentRead,
    LocalAgentUpdateRequest,
    ManualTagsUpdateRequest,
    OperationRuleCreateRequest,
    OperationRuleRead,
    OperationRuleUpdateRequest,
    NetworkEgressProfileCreateRequest,
    NetworkEgressProfileRead,
    PlatformAccountRead,
    PlatformAccountCreateRequest,
    PlatformAccountUpdateRequest,
    ProductOptions,
    RecommendationFeedTaskTemplateCreate,
    RecommendationFeedTaskTemplateUpdate,
    ReferenceLibraryBulkCreateFailure,
    ReferenceLibraryBulkCreateRequest,
    ReferenceLibraryBulkCreateResponse,
    ReferenceLibraryEventRead,
    ReferenceLibraryItemCreateRequest,
    ReferenceLibraryItemList,
    ReferenceLibraryItemRead,
    ReferenceLibraryReevaluateRequest,
    ReferenceLibraryReevaluateResponse,
    ReferenceLibraryReevaluateResult,
    ReferenceLibraryItemUpdateRequest,
    RiskPolicyCreateRequest,
    RiskPolicyRead,
    RoleRead,
    RuleProfileRead,
    RuleProfileUpdateRequest,
    TaskRunCreatedJob,
    TaskRunJobRead,
    TaskRunListResponse,
    TaskRunQueueContext,
    TaskRunRead,
    TaskScheduleCreateRequest,
    TaskScheduleRead,
    TaskScheduleUpdateRequest,
    TaskRunResponse,
    TaskTemplateCreateRequest,
    TaskTemplatePermissions,
    TaskTemplateReadiness,
    TaskTemplateListItem,
    TaskTemplateRead,
    TaskTemplateRunRequest,
    UserCreateRequest,
    UserPasswordResetRequest,
    UserRead,
    UserUpdateRequest,
    XhsSearchSuggestionRead,
    XhsSearchSuggestionTaskRequest,
)
from intelligence_engine.domain.user_intelligence_scenario_filter_schemas import (
    IntelligenceScenarioFilterListResponse,
    IntelligenceScenarioFilterRead,
    IntelligenceScenarioFilterUpsertRequest,
)
from intelligence_engine.audit.intelligence_center_audit import build_data_quality_overview
from intelligence_engine.domain.intelligence_pool import (
    aggregate_search_context,
    derive_data_status,
    extract_manual_tags,
    extract_platform_tags,
    extract_search_tags,
)
from intelligence_engine.storage.repositories.user_intelligence_scenario_filter_repository import (
    UserIntelligenceScenarioFilterRepository,
)
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.reference_library_repository import ReferenceLibraryRepository
from intelligence_engine.storage.repositories.manual_tag_repository import ManualTagRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.product_repository import ProductRepository
from intelligence_engine.services.intelligence_scenario_filter_service import (
    assert_custom_scenario_create,
    assert_valid_scenario,
    is_custom_scenario,
    filter_read_from_row,
    normalize_upsert_request,
)
from intelligence_engine.services.job_queue_diagnostics import build_task_run_queue_context
from intelligence_engine.services.task_materialization import TaskMaterializationService
from intelligence_engine.services.benchmark_selection import BenchmarkSelectionService, SelectionActor
from intelligence_engine.services.manual_tag_service import ManualTagActionError, ManualTagService
from intelligence_engine.services.rule_profile import RuleProfileService
from intelligence_engine.storage.repositories.operation_rule_repository import OperationRuleRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository
from intelligence_engine.domain.enums import ContentWorkflowStatus, CandidateBucket, SourceSurface, TaskRunStatus, TaskRunTriggerType
from intelligence_engine.api.account_access import (
    ensure_account_readable,
    ensure_account_writable,
    ensure_agent_readable,
    get_principal_employee_id,
    set_agent_employee,
)
from intelligence_engine.api.task_template_access import (
    ensure_business_type_in_scope,
    ensure_executor_account_for_template,
    ensure_schedule_writable,
    ensure_template_readable,
    ensure_template_schedule_creatable,
    ensure_template_deletable,
    ensure_template_writable,
    list_visible_business_type_ids,
    template_permissions,
    validate_template_bindings,
)
from intelligence_engine.services.agent_presence import effective_agent_status, sync_agent_presence
from intelligence_engine.services.media_service import MediaService
from intelligence_engine.security.auth import Principal, get_optional_principal, require_any_role
from intelligence_engine.security.intelligence_access import (
    INTELLIGENCE_READ_ROLES,
    ensure_can_revoke_reference_library_item,
    resolve_operator_intelligence_list_scope,
)
from intelligence_engine.services.account_login_service import AccountLoginService
from intelligence_engine.services.employee_agent_pool import (
    AgentEmployeeConflictError,
    account_session_health_for_employee_pool,
    register_agents_to_employee,
    resolve_discovered_agents,
)
from intelligence_engine.security.passwords import hash_password

router = APIRouter(prefix="/api")


def _enum_value(value):
    return getattr(value, "value", value)


def _local_agent_read(db: Session, agent: LocalAgent) -> LocalAgentRead:
    return LocalAgentRead(
        id=agent.id,
        employee_id=agent.employee_id,
        employee_display_name=_employee_name(db, agent.employee_id),
        device_name=agent.device_name,
        machine_fingerprint=agent.machine_fingerprint,
        status=effective_agent_status(agent),
        agent_version=agent.agent_version,
        capabilities=agent.capabilities_json or {},
        last_heartbeat_at=agent.last_heartbeat_at,
    )


def _list_local_agent_reads(db: Session, agents: list[LocalAgent]) -> list[LocalAgentRead]:
    if any(sync_agent_presence(agent) for agent in agents):
        db.flush()
    return [_local_agent_read(db, agent) for agent in agents]


def _employee_name(db: Session, employee_id: str | None) -> str | None:
    return db.get(Employee, employee_id).display_name if employee_id and db.get(Employee, employee_id) else None


def _business_type(db: Session, business_account_type_id: str | None) -> BusinessAccountType | None:
    return db.get(BusinessAccountType, business_account_type_id) if business_account_type_id else None


def _operator_business_type_ids(db: Session, principal: Principal) -> set[str]:
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        raise HTTPException(status_code=403, detail="operator has no employee profile")
    rows = db.scalars(
        select(PlatformAccount.business_account_type_id)
        .where(PlatformAccount.employee_id == employee_id)
        .where(PlatformAccount.business_account_type_id.is_not(None))
        .distinct()
    )
    return {item for item in rows if item}


def _employee_fetch_account(db: Session, employee_id: str) -> PlatformAccount | None:
    base = (
        select(PlatformAccount)
        .where(PlatformAccount.employee_id == employee_id)
        .where(PlatformAccount.status == AccountStatus.ACTIVE.value)
        .where(PlatformAccount.auth_status == AuthStatus.ACTIVE.value)
    )
    ordering = (
        PlatformAccount.last_success_at.desc(),
        PlatformAccount.last_verified_at.desc(),
        PlatformAccount.updated_at.desc(),
    )
    account = db.scalar(
        base.where(PlatformAccount.account_role == AccountRole.INTELLIGENCE_COLLECTOR.value)
        .order_by(*ordering)
        .limit(1)
    )
    if account:
        return account
    return db.scalar(base.order_by(*ordering).limit(1))


def _manual_fetch_account_id(db: Session, repo: ContentRepository, *, content_id: str, principal: Principal) -> str | None:
    if not db.get(ContentIdentity, content_id):
        raise ValueError("content not found")
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        return repo.latest_discovery_account_id(content_id)
    account = _employee_fetch_account(db, employee_id)
    if not account:
        raise HTTPException(status_code=409, detail="operator has no active account for manual fetch")
    return account.id


def _ensure_operator_has_business_types(db: Session, principal: Principal) -> tuple[str, set[str]]:
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        raise HTTPException(status_code=403, detail="operator has no employee profile")
    business_type_ids = _operator_business_type_ids(db, principal)
    if not business_type_ids:
        raise HTTPException(status_code=409, detail="当前运营账号未配置业务类型，请先在账号管理中配置后再创建")
    return employee_id, business_type_ids


def _group_submitter_name(db: Session, group: BenchmarkGroup) -> str | None:
    if not group.owner_employee_id:
        return None
    employee = db.get(Employee, group.owner_employee_id)
    return employee.display_name if employee else None


def _rule_set_submitter_name(db: Session, row: KeywordRuleSet) -> str | None:
    if row.created_by_employee_id:
        employee = db.get(Employee, row.created_by_employee_id)
        if employee:
            return employee.display_name
    if row.created_by_user_id:
        user = db.get(User, row.created_by_user_id)
        if user:
            return user.display_name
    return None


def _benchmark_group_read(db: Session, group: BenchmarkGroup) -> BenchmarkGroupRead:
    employee = db.get(Employee, group.owner_employee_id) if group.owner_employee_id else None
    return BenchmarkGroupRead(
        id=group.id,
        name=group.name,
        description=group.description,
        owner_employee_id=group.owner_employee_id,
        submitter_user_id=employee.user_id if employee else None,
        submitter_employee_id=group.owner_employee_id,
        submitter_name=employee.display_name if employee else None,
        enabled=group.enabled,
        metadata=group.metadata_json or {},
    )


def _keyword_rule_set_read(db: Session, row: KeywordRuleSet) -> KeywordRuleSetRead:
    config = {
        "visible_like_threshold": 50,
        "lead_intent_keywords": ["求推", "求推荐", "推一下", "求渠道", "有没有推荐"],
        **(row.config_json or {}),
    }
    return KeywordRuleSetRead(
        id=row.id,
        name=row.name,
        rule_scope=row.rule_scope,
        enabled=row.enabled,
        created_by_user_id=row.created_by_user_id,
        created_by_employee_id=row.created_by_employee_id,
        submitter_name=_rule_set_submitter_name(db, row),
        config=config,
    )


def _is_operator(principal: Principal) -> bool:
    return principal.has_role(UserRoleName.OPERATOR) and not principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)


def _ensure_benchmark_group_readable(db: Session, principal: Principal, group: BenchmarkGroup) -> None:
    if not _is_operator(principal):
        return
    business_type_ids = _operator_business_type_ids(db, principal)
    if not business_type_ids:
        raise HTTPException(status_code=403, detail="operator has no business account type scope")
    binding = db.scalar(
        select(BusinessAccountTypeBenchmarkGroup.id).where(
            BusinessAccountTypeBenchmarkGroup.benchmark_group_id == group.id,
            BusinessAccountTypeBenchmarkGroup.business_account_type_id.in_(list(business_type_ids)),
        )
    )
    if not binding:
        raise HTTPException(status_code=403, detail="insufficient permission for this benchmark group")


def _ensure_benchmark_group_writable(db: Session, principal: Principal, group: BenchmarkGroup) -> None:
    if not _is_operator(principal):
        return
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        raise HTTPException(status_code=403, detail="operator has no employee profile")
    if group.owner_employee_id != employee_id:
        raise HTTPException(status_code=403, detail="仅提交人可编辑/删除该对标组")


def _ensure_rule_set_readable(db: Session, principal: Principal, rule_set: KeywordRuleSet) -> None:
    if not _is_operator(principal):
        return
    business_type_ids = _operator_business_type_ids(db, principal)
    if not business_type_ids:
        raise HTTPException(status_code=403, detail="operator has no business account type scope")
    binding = db.scalar(
        select(BusinessAccountTypeRuleSet.id).where(
            BusinessAccountTypeRuleSet.rule_set_id == rule_set.id,
            BusinessAccountTypeRuleSet.business_account_type_id.in_(list(business_type_ids)),
        )
    )
    if not binding:
        raise HTTPException(status_code=403, detail="insufficient permission for this rule set")


def _ensure_rule_set_writable(db: Session, principal: Principal, rule_set: KeywordRuleSet) -> None:
    if not _is_operator(principal):
        return
    if rule_set.created_by_user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="仅提交人可编辑/删除该业务规则")


def _account_read(db: Session, repo: ProductRepository, account: PlatformAccount) -> PlatformAccountRead:
    business_type = _business_type(db, account.business_account_type_id)
    active_login = AccountLoginService(db).get_active_session(account.id)
    session_health_status = account_session_health_for_employee_pool(db, account) or repo.latest_session_status(account.id)
    active_login_session_status = active_login.status if active_login else None
    return PlatformAccountRead(
        id=account.id,
        employee_id=account.employee_id,
        employee_display_name=_employee_name(db, account.employee_id),
        platform=account.platform,
        display_name=account.display_name,
        external_account_id=account.external_account_id,
        business_account_type_id=account.business_account_type_id,
        business_account_type_name=business_type.name if business_type else None,
        legacy_business_account_type=account.business_account_type,
        status=account.status,
        auth_status=getattr(account, "auth_status", None) or "not_logged_in",
        account_role=getattr(account, "account_role", None) or AccountRole.INTELLIGENCE_COLLECTOR.value,
        health_status=getattr(account, "health_status", None) or "healthy",
        profile_key=getattr(account, "profile_key", None),
        platform_nickname=getattr(account, "platform_nickname", None),
        platform_home_url=getattr(account, "platform_home_url", None),
        last_verified_at=getattr(account, "last_verified_at", None),
        login_cdp_port=getattr(account, "login_cdp_port", None),
        default_agent_id=getattr(account, "default_agent_id", None),
        bindings=[],
        session_health_status=session_health_status,
        active_login_session_status=active_login_session_status,
        usage_status=_derive_account_usage_status(
            status=account.status,
            auth_status=getattr(account, "auth_status", None) or "not_logged_in",
            session_health_status=session_health_status,
            active_login_session_status=active_login_session_status,
        ),
        last_success_at=account.last_success_at,
        last_failure_at=account.last_failure_at,
        consecutive_failures=account.consecutive_failures,
        metadata=account.metadata_json or {},
    )


def _account_binding_reads(db: Session, account_id: str) -> list[AccountAgentBindingRead]:
    rows = list(
        db.scalars(
            select(AccountAgentBinding)
            .where(AccountAgentBinding.account_id == account_id)
            .where(AccountAgentBinding.enabled.is_(True))
            .order_by(AccountAgentBinding.updated_at.desc())
        )
    )
    result: list[AccountAgentBindingRead] = []
    for row in rows:
        agent = db.get(LocalAgent, row.agent_id)
        session_status = db.scalar(
            select(AccountSession.status)
            .where(AccountSession.account_id == account_id, AccountSession.local_agent_id == row.agent_id)
            .order_by(AccountSession.last_validated_at.desc().nullslast(), AccountSession.created_at.desc())
            .limit(1)
        )
        result.append(
            AccountAgentBindingRead(
                id=row.id,
                account_id=row.account_id,
                agent_id=row.agent_id,
                employee_id=row.employee_id,
                agent_device_name=agent.device_name if agent else None,
                agent_status=effective_agent_status(agent) if agent else None,
                enabled=row.enabled,
                session_status=session_status,
                last_claimed_at=row.last_claimed_at,
            )
        )
    return result


def _best_binding_session_status(bindings: list[AccountAgentBindingRead]) -> str | None:
    statuses = [item.session_status for item in bindings if item.session_status]
    if not statuses:
        return None
    if "ready" in statuses:
        return "ready"
    if "manual_verify_required" in statuses:
        return "manual_verify_required"
    if "expired" in statuses:
        return "expired"
    return statuses[0]


def _derive_account_usage_status(
    *,
    status: str,
    auth_status: str,
    session_health_status: str | None,
    active_login_session_status: str | None,
) -> str:
    status_value = (status or "").lower()
    auth_value = (auth_status or "").lower()
    session_value = (session_health_status or "").lower()
    login_value = (active_login_session_status or "").lower()
    if status_value in {"disabled", "paused"}:
        return "unavailable"
    if "manual_verify" in session_value or login_value == "waiting_user_login":
        return "need_verify"
    if auth_value in {"not_logged_in", "expired", "error", "login_pending"}:
        return "need_login"
    if session_value and session_value != "ready":
        return "unavailable"
    if auth_value == "active":
        return "ready"
    return "unavailable"


def _task_template_read(service: TaskMaterializationService, template: TaskTemplate) -> TaskTemplateRead:
    from intelligence_engine.services.task_template_config import parse_template_config_dict, strip_legacy_template_config_keys

    config = strip_legacy_template_config_keys(parse_template_config_dict(template.config_json))
    typed_payload = service.read_template_config(template.template_type, config)
    return TaskTemplateRead(
        id=template.id,
        name=template.name,
        template_type=template.template_type,
        platform=template.platform,
        account_id=template.account_id,
        business_account_type_id=template.business_account_type_id,
        config=config,
        enabled=template.enabled,
        typed_payload=typed_payload,
    )


def _workflow_read(state) -> ContentWorkflowRead:
    return ContentWorkflowRead(
        content_id=state.content_id,
        workflow_status=state.workflow_status,
        assigned_to_user_id=state.assigned_to_user_id,
        assigned_by_user_id=state.assigned_by_user_id,
        assigned_at=state.assigned_at,
        reviewed_at=state.reviewed_at,
        selected_at=state.selected_at,
        discarded_at=state.discarded_at,
        latest_operator_note=state.latest_operator_note,
    )


def _option_values(enum_cls) -> list[dict[str, str]]:
    return [{"value": item.value, "label": item.value} for item in enum_cls]


def _product_options() -> ProductOptions:
    from intelligence_engine.domain.enums import FeedType, JobType

    return ProductOptions(
        roles=_option_values(UserRoleName),
        platforms=_option_values(Platform),
        feed_types=_option_values(FeedType),
        task_template_types=[
            {"value": "recommendation_feed_task", "label": "recommendation_feed_task"},
            {"value": "creator_monitor_task", "label": "creator_monitor_task"},
            {"value": "keyword_search_task", "label": "keyword_search_task"},
        ],
        workflow_statuses=_option_values(ContentWorkflowStatus),
        candidate_buckets=_option_values(CandidateBucket),
        account_statuses=_option_values(AccountStatus),
        agent_statuses=_option_values(AgentStatus),
    )


def _task_template_key_fields(template: TaskTemplate) -> dict:
    config = template.config_json or {}
    keys = ("feed_type", "target_count", "benchmark_group_id", "platform", "keywords", "max_items", "rule_set_id")
    return {key: config.get(key) for key in keys if key in config}


def _readiness_from_checks(checks: list[dict]) -> TaskTemplateReadiness:
    messages = [item["message"] for item in checks if not item["ok"]]
    return TaskTemplateReadiness(ready=not messages, checks=checks, messages=messages)


def _template_readiness(service: TaskMaterializationService, template: TaskTemplate) -> TaskTemplateReadiness:
    return _readiness_from_checks(service.template_readiness_checks(template))


def _run_readiness(service: TaskMaterializationService, template: TaskTemplate, executor_account_id: str) -> TaskTemplateReadiness:
    return _readiness_from_checks(service.run_readiness_checks(template, executor_account_id))


def _user_display_name(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user.display_name if user else None


def _task_template_list_item(db: Session, principal: Principal, template: TaskTemplate) -> TaskTemplateListItem:
    business_type = _business_type(db, template.business_account_type_id)
    perms = template_permissions(principal, template)
    return TaskTemplateListItem(
        id=template.id,
        name=template.name,
        template_type=template.template_type,
        enabled=template.enabled,
        platform=template.platform,
        business_account_type_id=template.business_account_type_id,
        business_account_type_name=business_type.name if business_type else None,
        created_by_user_id=template.created_by_user_id,
        created_by_display_name=_user_display_name(db, template.created_by_user_id),
        key_fields=_task_template_key_fields(template),
        permissions=TaskTemplatePermissions(**perms),
    )


def _schedule_read(schedule) -> TaskScheduleRead:
    return TaskScheduleRead(
        id=schedule.id,
        task_template_id=schedule.task_template_id,
        executor_account_id=schedule.executor_account_id,
        created_by_user_id=schedule.created_by_user_id,
        schedule_type=schedule.schedule_type,
        interval_seconds=schedule.interval_seconds,
        daily_time_window=schedule.daily_time_window_json or {},
        enabled=schedule.enabled,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        last_materialized_at=schedule.last_materialized_at,
    )


def _task_run_read(service: TaskMaterializationService, run: TaskRun, *, include_jobs: bool = True) -> TaskRunRead:
    run = service.refresh_task_run(run)
    jobs = list(
        service.db.scalars(select(Job).where(Job.task_run_id == run.id).order_by(Job.created_at.asc()))
    ) if include_jobs else []
    queue = build_task_run_queue_context(service.db, run)
    return TaskRunRead(
        id=run.id,
        task_template_id=run.task_template_id,
        trigger_type=run.trigger_type,
        requested_by_user_id=run.requested_by_user_id,
        task_schedule_id=run.task_schedule_id,
        status=run.status,
        jobs_total=run.jobs_total,
        jobs_pending=run.jobs_pending,
        jobs_running=run.jobs_running,
        jobs_success=run.jobs_success,
        jobs_failed=run.jobs_failed,
        result_summary=run.result_summary_json or {},
        error_summary=run.error_summary_json or {},
        jobs=[
            TaskRunJobRead(
                job_id=job.id,
                job_type=job.job_type,
                status=job.status,
                account_id=job.account_id,
                claimed_by_agent_id=job.claimed_by_agent_id,
                result_summary=job.result_summary_json or {},
                error_message=job.last_error_message,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
            )
            for job in jobs
        ],
        queue_context=TaskRunQueueContext(
            waiting_reason=queue["waiting_reason"],
            message=queue["message"],
            pending_jobs_ahead=queue.get("pending_jobs_ahead", 0),
            job_priority=queue.get("job_priority"),
            agent_running_job_id=queue.get("agent_running_job_id"),
            agent_running_job_type=queue.get("agent_running_job_type"),
            agent_running_since=queue.get("agent_running_since"),
        ),
        created_at=run.created_at,
        updated_at=run.updated_at,
        finished_at=run.finished_at,
    )


def _create_manual_fetch_task_run(
    db: Session,
    *,
    account_id: str | None,
    requested_by_user_id: str | None,
) -> TaskRun:
    run = TaskRun(
        task_template_id=None,
        trigger_type=TaskRunTriggerType.MANUAL.value,
        requested_by_user_id=requested_by_user_id,
        executor_account_id=account_id,
        status=TaskRunStatus.MATERIALIZED.value,
        result_summary_json={},
        error_summary_json={},
    )
    db.add(run)
    db.flush()
    return run


def _create_typed_task_template(
    db: Session,
    *,
    name: str,
    enabled: bool,
    template_type: str,
    business_account_type_id: str,
    created_by_user_id: str | None,
    payload: dict,
    platform: str | None = None,
) -> TaskTemplate:
    service = TaskMaterializationService(db)
    config = service.validate_template_config(template_type, payload)
    require_benchmark = template_type == "creator_monitor_task"
    validate_template_bindings(
        db,
        business_account_type_id=business_account_type_id,
        rule_set_id=config.get("rule_set_id"),
        benchmark_group_id=config.get("benchmark_group_id"),
        require_benchmark=require_benchmark,
    )
    return ProductRepository(db).create_task_template(
        name=name,
        template_type=template_type,
        platform=platform or config.get("platform"),
        business_account_type_id=business_account_type_id,
        created_by_user_id=created_by_user_id,
        config=config,
        enabled=enabled,
    )


def _update_typed_task_template(db: Session, template: TaskTemplate, request) -> TaskTemplate:
    service = TaskMaterializationService(db)
    patch = request.model_dump(exclude_unset=True, mode="json")
    name = patch.pop("name", None)
    enabled = patch.pop("enabled", None)
    business_account_type_id = patch.pop("business_account_type_id", None)
    config = dict(template.config_json or {})
    config.update(patch)
    config = service.validate_template_config(template.template_type, config)
    effective_business_type_id = business_account_type_id or template.business_account_type_id
    if not effective_business_type_id:
        raise HTTPException(status_code=400, detail="business account type is required")
    require_benchmark = template.template_type == "creator_monitor_task"
    validate_template_bindings(
        db,
        business_account_type_id=effective_business_type_id,
        rule_set_id=config.get("rule_set_id"),
        benchmark_group_id=config.get("benchmark_group_id"),
        require_benchmark=require_benchmark,
    )
    return ProductRepository(db).update_task_template(
        template,
        name=name,
        enabled=enabled,
        business_account_type_id=business_account_type_id,
        config=config,
    )


_TASK_TEMPLATE_READ_ROLES = (UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)


def _user_read(repo: ProductRepository, user: User) -> UserRead:
    employee = repo.get_employee_for_user(user.id)
    return UserRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        status=user.status,
        roles=repo.user_role_names(user.id),
        created_at=user.created_at,
        employee_id=employee.id if employee else None,
    )


def _employee_list_item(repo: ProductRepository, employee: Employee, account_counts: dict[str, int], agent_counts: dict[str, int]) -> EmployeeListItem:
    user = repo.get_user(employee.user_id) if employee.user_id else None
    return EmployeeListItem(
        id=employee.id,
        user_id=employee.user_id,
        display_name=employee.display_name,
        email=employee.email,
        status=employee.status,
        user_username=user.username if user else None,
        user_display_name=user.display_name if user else None,
        account_count=account_counts.get(employee.id, 0),
        agent_count=agent_counts.get(employee.id, 0),
    )


def _ensure_content(content_id: str, db: Session) -> ContentIdentity:
    content = db.get(ContentIdentity, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="content not found")
    return content


def _rule_profile_read(profile) -> RuleProfileRead:
    return RuleProfileRead(
        id=profile.id,
        name=profile.name,
        platform=profile.platform,
        library_type=profile.library_type,
        version=profile.version,
        enabled=profile.enabled,
        config=profile.config_json or {},
        created_by_user_id=profile.created_by_user_id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _operation_rule_read(rule: OperationRule) -> OperationRuleRead:
    return OperationRuleRead(
        id=rule.id,
        rule_type=rule.rule_type,
        title=rule.title,
        content=rule.content,
        platform=rule.platform,
        enabled=rule.enabled,
        version=rule.version,
        created_by_user_id=rule.created_by_user_id,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _reference_library_event_read(event) -> ReferenceLibraryEventRead:
    return ReferenceLibraryEventRead(
        id=event.id,
        library_item_id=event.library_item_id,
        content_id=event.content_id,
        event_type=event.event_type,
        user_id=event.user_id,
        employee_id=event.employee_id,
        event_payload=event.event_payload_json or {},
        created_at=event.created_at,
    )


@router.post("/product/bootstrap-default-roles", response_model=list[RoleRead])
def bootstrap_default_roles(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    roles = repo.ensure_default_roles()
    db.commit()
    return [RoleRead(id=role.id, name=role.name, description=role.description) for role in roles]


@router.post("/users", response_model=UserRead)
def create_user(request: UserCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    if repo.get_user_by_username(request.username):
        raise HTTPException(status_code=409, detail="username already exists")
    user = repo.create_user(
        username=request.username,
        display_name=request.display_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role_names=[_enum_value(role) for role in request.role_names],
        metadata=request.metadata,
    )
    db.commit()
    return _user_read(repo, user)


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    return [_user_read(repo, user) for user in repo.list_users()]


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    repo.update_user(
        user,
        display_name=request.display_name,
        email=request.email,
        status=request.status,
        role_names=[_enum_value(role) for role in request.role_names] if request.role_names is not None else None,
    )
    db.commit()
    return _user_read(repo, user)


@router.post("/users/{user_id}/reset-password", response_model=UserRead)
def reset_user_password(
    user_id: str,
    request: UserPasswordResetRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    repo.set_password(user, hash_password(request.password))
    db.commit()
    return _user_read(repo, user)


@router.post("/employees", response_model=EmployeeRead)
def create_employee(request: EmployeeCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    employee = ProductRepository(db).create_employee(user_id=request.user_id, display_name=request.display_name, email=request.email, status=request.status)
    db.commit()
    return EmployeeRead(id=employee.id, user_id=employee.user_id, display_name=employee.display_name, email=employee.email, status=employee.status)


@router.post("/employees/with-user", response_model=EmployeeListItem)
def create_employee_with_user(
    request: EmployeeWithUserCreateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    if repo.get_user_by_username(request.username):
        raise HTTPException(status_code=409, detail="username already exists")
    user, employee = repo.create_employee_with_user(
        username=request.username,
        display_name=request.display_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role_name=_enum_value(request.role),
    )
    db.commit()
    return _employee_list_item(repo, employee, repo.employee_account_counts(), repo.employee_agent_counts())


@router.get("/employees", response_model=list[EmployeeListItem])
def list_employees(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    repo = ProductRepository(db)
    account_counts = repo.employee_account_counts()
    agent_counts = repo.employee_agent_counts()
    return [_employee_list_item(repo, employee, account_counts, agent_counts) for employee in repo.list_employees()]


@router.patch("/employees/{employee_id}", response_model=EmployeeListItem)
def update_employee(
    employee_id: str,
    request: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ProductRepository(db)
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")
    if request.display_name is not None:
        employee.display_name = request.display_name
    if request.email is not None:
        employee.email = request.email
    if request.status is not None:
        employee.status = request.status
    if request.user_id is not None:
        employee.user_id = request.user_id
    db.flush()
    db.commit()
    return _employee_list_item(repo, employee, repo.employee_account_counts(), repo.employee_agent_counts())


@router.post("/product/me/local-agents/resolve-discover", response_model=list[ResolvedDiscoverMatch])
def resolve_my_discovered_local_agents(
    request: ResolveDiscoveredAgentsRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.OPERATOR, UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    if not request.items:
        raise HTTPException(status_code=400, detail="items required")
    pairs = resolve_discovered_agents(
        db,
        [item.model_dump() for item in request.items],
    )
    db.commit()
    return [
        ResolvedDiscoverMatch(agent=_local_agent_read(db, agent), bridge_port=bridge_port)
        for agent, bridge_port in pairs
    ]


@router.post("/product/me/local-agents/register", response_model=list[LocalAgentRead])
def register_my_local_agents(
    request: RegisterLocalAgentsRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.OPERATOR, UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    employee_id = get_principal_employee_id(db, principal)
    if not employee_id:
        raise HTTPException(status_code=403, detail="operator has no employee profile")
    if not request.agent_ids:
        raise HTTPException(status_code=400, detail="agent_ids required")
    try:
        agents = register_agents_to_employee(
            db,
            agent_ids=request.agent_ids,
            employee_id=employee_id,
            force=request.force,
        )
    except AgentEmployeeConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agent_bound_conflict",
                "agent_id": exc.agent_id,
                "bound_employee_id": exc.bound_employee_id,
                "message": "agent already bound to another employee",
            },
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return _list_local_agent_reads(db, agents)


def _require_authenticated_user_id(principal: Principal) -> str:
    if not principal.user_id:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal.user_id


@router.get("/product/me/intelligence/scenario-filters", response_model=IntelligenceScenarioFilterListResponse)
def list_my_intelligence_scenario_filters(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    user_id = _require_authenticated_user_id(principal)
    repo = UserIntelligenceScenarioFilterRepository(db)
    items = [filter_read_from_row(row) for row in repo.list_for_user(user_id)]
    return IntelligenceScenarioFilterListResponse(items=items)


@router.get("/product/me/intelligence/scenario-filters/{scenario}", response_model=IntelligenceScenarioFilterRead)
def get_my_intelligence_scenario_filter(
    scenario: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    try:
        assert_valid_scenario(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_id = _require_authenticated_user_id(principal)
    row = UserIntelligenceScenarioFilterRepository(db).get(user_id, scenario)
    if row is None:
        raise HTTPException(status_code=404, detail="scenario filter not customized")
    return filter_read_from_row(row)


@router.put("/product/me/intelligence/scenario-filters/{scenario}", response_model=IntelligenceScenarioFilterRead)
def upsert_my_intelligence_scenario_filter(
    scenario: str,
    request: IntelligenceScenarioFilterUpsertRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.OPERATOR, UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    try:
        assert_valid_scenario(scenario)
        assert_custom_scenario_create(scenario, request.rolling)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_id = _require_authenticated_user_id(principal)
    filters_json, rolling_json = normalize_upsert_request(request)
    repo = UserIntelligenceScenarioFilterRepository(db)
    if is_custom_scenario(scenario) and repo.get(user_id, scenario) is None:
        existing_custom = [row for row in repo.list_for_user(user_id) if is_custom_scenario(row.scenario)]
        if len(existing_custom) >= 20:
            raise HTTPException(status_code=400, detail="custom scenario limit reached")
    row = repo.upsert(
        user_id,
        scenario,
        filters_json,
        rolling_json,
    )
    db.commit()
    return filter_read_from_row(row)


@router.delete("/product/me/intelligence/scenario-filters/{scenario}", status_code=204)
def delete_my_intelligence_scenario_filter(
    scenario: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.OPERATOR, UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    try:
        assert_valid_scenario(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_id = _require_authenticated_user_id(principal)
    deleted = UserIntelligenceScenarioFilterRepository(db).delete(user_id, scenario)
    if not deleted:
        raise HTTPException(status_code=404, detail="scenario filter not customized")
    db.commit()


@router.get("/local-agents", response_model=list[LocalAgentRead])
def list_local_agents(
    employee_id: str | None = None,
    status: AgentStatus | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    repo = ProductRepository(db)
    scoped_employee = get_principal_employee_id(db, principal)
    if scoped_employee:
        agents = repo.list_bindable_agents_for_employee(scoped_employee)
        if status:
            status_value = _enum_value(status)
            agents = [agent for agent in agents if effective_agent_status(agent) == status_value]
    else:
        agents = repo.list_agents(employee_id=employee_id, status=_enum_value(status) if status else None)
        from intelligence_engine.services.agent_selection import sort_agents_for_display

        agents = sort_agents_for_display(agents)
    reads = _list_local_agent_reads(db, agents)
    db.commit()
    return reads


@router.get("/local-agents/{agent_id}", response_model=LocalAgentRead)
def get_local_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    agent = db.get(LocalAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    ensure_agent_readable(db, principal, agent)
    if sync_agent_presence(agent):
        db.flush()
    db.commit()
    return _local_agent_read(db, agent)


@router.patch("/local-agents/{agent_id}", response_model=LocalAgentRead)
def update_local_agent(
    agent_id: str,
    request: LocalAgentUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    if not request.model_fields_set:
        raise HTTPException(status_code=400, detail="no fields to update")
    agent = db.get(LocalAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    if "employee_id" in request.model_fields_set:
        agent = set_agent_employee(db, agent_id=agent_id, employee_id=request.employee_id)
    if "status" in request.model_fields_set and request.status is not None:
        allowed = {AgentStatus.RETIRED.value, AgentStatus.OFFLINE.value}
        if request.status not in allowed:
            raise HTTPException(status_code=400, detail="unsupported agent status")
        agent.status = request.status
    if sync_agent_presence(agent) and agent.status != AgentStatus.RETIRED.value:
        db.flush()
    db.commit()
    return _local_agent_read(db, agent)


@router.post("/business-account-types", response_model=BusinessAccountTypeRead)
def create_business_account_type(request: BusinessAccountTypeCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    item = ProductRepository(db).create_business_account_type(name=request.name, description=request.description, enabled=request.enabled)
    db.commit()
    return BusinessAccountTypeRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled)


@router.patch("/business-account-types/{business_account_type_id}", response_model=BusinessAccountTypeRead)
def update_business_account_type(business_account_type_id: str, request: BusinessAccountTypeUpdateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    item = db.get(BusinessAccountType, business_account_type_id)
    if not item:
        raise HTTPException(status_code=404, detail="business account type not found")
    repo = ProductRepository(db)
    item = repo.update_business_account_type(item, **request.model_dump(exclude_unset=True))
    db.commit()
    rule_count, group_count = repo.business_type_relation_counts(item.id)
    return BusinessAccountTypeRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled, rule_set_count=rule_count, benchmark_group_count=group_count)


@router.delete("/business-account-types/{business_account_type_id}", status_code=204)
def delete_business_account_type(business_account_type_id: str, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    item = db.get(BusinessAccountType, business_account_type_id)
    if not item:
        raise HTTPException(status_code=404, detail="business account type not found")
    repo = ProductRepository(db)
    rule_count, group_count = repo.business_type_relation_counts(item.id)
    account_count = repo.business_type_account_count(item.id)
    if rule_count or group_count or account_count:
        raise HTTPException(status_code=409, detail="业务账号类型已被账号、规则集或对标组引用，不能删除")
    repo.delete_business_account_type(item)
    db.commit()


@router.get("/business-account-types", response_model=list[BusinessAccountTypeRead])
def list_business_account_types(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    repo = ProductRepository(db)
    def read(item):
        rule_count, group_count = repo.business_type_relation_counts(item.id)
        return BusinessAccountTypeRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled, rule_set_count=rule_count, benchmark_group_count=group_count)
    return [
        read(item)
        for item in repo.list_business_account_types()
    ]


@router.get("/product/accounts", response_model=list[PlatformAccountRead])
def list_product_accounts(
    employee_id: str | None = None,
    platform: Platform | None = None,
    status: AccountStatus | None = None,
    business_account_type_id: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    scoped_employee = get_principal_employee_id(db, principal)
    if scoped_employee:
        employee_id = scoped_employee
    repo = ProductRepository(db)
    accounts = repo.list_accounts(
        employee_id=employee_id,
        platform=_enum_value(platform) if platform else None,
        status=_enum_value(status) if status else None,
        business_account_type_id=business_account_type_id,
    )
    return [_account_read(db, repo, account) for account in accounts]


@router.post("/product/accounts", response_model=PlatformAccountRead)
def create_product_account(
    request: PlatformAccountCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    scoped_employee = get_principal_employee_id(db, principal)
    employee_id = request.employee_id
    if scoped_employee and employee_id and employee_id != scoped_employee:
        raise HTTPException(status_code=403, detail="operator can only create accounts for self")
    if scoped_employee and not employee_id:
        employee_id = scoped_employee
    repo = ProductRepository(db)
    account = repo.create_account(
        employee_id=employee_id,
        platform=_enum_value(request.platform),
        display_name=request.display_name,
        external_account_id=request.external_account_id,
        business_account_type=request.business_account_type,
        business_account_type_id=request.business_account_type_id,
        default_agent_id=request.default_agent_id,
        account_role=request.account_role,
        health_status=request.health_status,
        metadata=request.metadata,
    )
    db.commit()
    return _account_read(db, repo, account)


@router.get("/product/accounts/{account_id}", response_model=PlatformAccountRead)
def get_product_account(
    account_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_readable(db, principal, account)
    repo = ProductRepository(db)
    return _account_read(db, repo, account)


@router.patch("/product/accounts/{account_id}", response_model=PlatformAccountRead)
def update_product_account(
    account_id: str,
    request: PlatformAccountUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_writable(db, principal, account)
    repo = ProductRepository(db)
    payload = request.model_dump(exclude_unset=True)
    updated = repo.update_account(account, **payload)
    if "default_agent_id" in payload:
        AccountLoginService(db).reroute_waiting_sessions_for_account(updated, agent_id=payload.get("default_agent_id"))
    db.commit()
    return _account_read(db, repo, updated)


@router.get("/product/accounts/{account_id}/agent-bindings", response_model=list[AccountAgentBindingRead])
def list_account_agent_bindings(
    account_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_readable(db, principal, account)
    return _account_binding_reads(db, account_id)


@router.post("/product/accounts/{account_id}/agent-bindings", response_model=list[AccountAgentBindingRead])
def create_account_agent_bindings(
    account_id: str,
    request: AccountAgentBindingCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_writable(db, principal, account)
    scoped_employee = get_principal_employee_id(db, principal)
    target_employee = scoped_employee or account.employee_id
    for agent_id in request.agent_ids:
        agent = db.get(LocalAgent, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent not found: {agent_id}")
        if agent.employee_id and target_employee and agent.employee_id != target_employee and not request.force:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "agent_bound_conflict",
                    "agent_id": agent.id,
                    "bound_employee_id": agent.employee_id,
                    "message": "agent already bound to another employee",
                },
            )
        if target_employee and (agent.employee_id is None or request.force):
            agent.employee_id = target_employee
        ProductRepository(db).ensure_account_agent_binding(
            account_id=account_id,
            agent_id=agent.id,
            employee_id=agent.employee_id,
        )
    db.commit()
    return _account_binding_reads(db, account_id)


@router.post("/product/accounts/{account_id}/agent-bindings/{agent_id}/rebind", response_model=list[AccountAgentBindingRead])
def rebind_account_agent_binding(
    account_id: str,
    agent_id: str,
    request: AccountAgentBindingRebindRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_writable(db, principal, account)
    agent = db.get(LocalAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    scoped_employee = get_principal_employee_id(db, principal)
    target_employee = scoped_employee or account.employee_id
    if agent.employee_id and target_employee and agent.employee_id != target_employee and not request.force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agent_bound_conflict",
                "agent_id": agent.id,
                "bound_employee_id": agent.employee_id,
                "message": "agent already bound to another employee",
            },
        )
    if target_employee:
        agent.employee_id = target_employee
    ProductRepository(db).ensure_account_agent_binding(account_id=account_id, agent_id=agent.id, employee_id=agent.employee_id)
    db.commit()
    return _account_binding_reads(db, account_id)


@router.delete("/product/accounts/{account_id}/agent-bindings/{agent_id}", response_model=list[AccountAgentBindingRead])
def delete_account_agent_binding(
    account_id: str,
    agent_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    account = db.get(PlatformAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    ensure_account_writable(db, principal, account)
    ProductRepository(db).disable_account_agent_binding(account_id=account_id, agent_id=agent_id)
    db.commit()
    return _account_binding_reads(db, account_id)


@router.post("/benchmark-groups", response_model=BenchmarkGroupRead)
def create_benchmark_group(
    request: BenchmarkGroupCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    owner_employee_id = request.owner_employee_id
    auto_bind_business_types: set[str] = set()
    if _is_operator(principal):
        owner_employee_id, auto_bind_business_types = _ensure_operator_has_business_types(db, principal)
    group = ProductRepository(db).create_benchmark_group(
        name=request.name,
        description=request.description,
        owner_employee_id=owner_employee_id,
        enabled=request.enabled,
        metadata=request.metadata,
    )
    if _is_operator(principal):
        for business_type_id in auto_bind_business_types:
            ProductRepository(db).bind_business_type_to_benchmark_group(
                business_account_type_id=business_type_id,
                benchmark_group_id=group.id,
            )
    db.commit()
    return _benchmark_group_read(db, group)


@router.patch("/benchmark-groups/{group_id}", response_model=BenchmarkGroupRead)
def update_benchmark_group(
    group_id: str,
    request: BenchmarkGroupUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    _ensure_benchmark_group_writable(db, principal, group)
    group = ProductRepository(db).update_benchmark_group(group, **request.model_dump(exclude_unset=True))
    db.commit()
    return _benchmark_group_read(db, group)


@router.delete("/benchmark-groups/{group_id}", status_code=204)
def delete_benchmark_group(
    group_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    _ensure_benchmark_group_writable(db, principal, group)
    ProductRepository(db).delete_benchmark_group(group)
    db.commit()


@router.get("/benchmark-groups", response_model=list[BenchmarkGroupRead])
def list_benchmark_groups(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    groups = ProductRepository(db).list_benchmark_groups()
    if _is_operator(principal):
        business_type_ids = _operator_business_type_ids(db, principal)
        if not business_type_ids:
            return []
        allowed_group_ids = set(
            db.scalars(
                select(BusinessAccountTypeBenchmarkGroup.benchmark_group_id).where(
                    BusinessAccountTypeBenchmarkGroup.business_account_type_id.in_(list(business_type_ids))
                )
            )
        )
        groups = [group for group in groups if group.id in allowed_group_ids]
    return [_benchmark_group_read(db, group) for group in groups]


@router.post("/benchmark-groups/{group_id}/members", response_model=BenchmarkGroupMemberRead)
def add_benchmark_group_member(
    group_id: str,
    request: BenchmarkGroupMemberCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    _ensure_benchmark_group_writable(db, principal, group)
    member = ProductRepository(db).add_benchmark_member(
        benchmark_group_id=group_id,
        creator_monitor_id=request.creator_monitor_id,
        platform=_enum_value(request.platform),
        creator_platform_id=request.creator_platform_id,
        creator_profile_url=request.creator_profile_url,
        display_name=request.display_name,
        platform_context=request.platform_context,
        enabled=request.enabled,
    )
    db.commit()
    return BenchmarkGroupMemberRead(
        id=member.id,
        benchmark_group_id=member.benchmark_group_id,
        creator_monitor_id=member.creator_monitor_id,
        platform=member.platform,
        creator_platform_id=member.creator_platform_id,
        creator_profile_url=member.creator_profile_url,
        display_name=member.display_name,
        platform_context=member.platform_context_json,
        enabled=member.enabled,
    )


@router.get("/benchmark-groups/{group_id}/members", response_model=list[BenchmarkGroupMemberRead])
def list_benchmark_group_members(
    group_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    return [
        BenchmarkGroupMemberRead(
            id=member.id,
            benchmark_group_id=member.benchmark_group_id,
            creator_monitor_id=member.creator_monitor_id,
            platform=member.platform,
            creator_platform_id=member.creator_platform_id,
            creator_profile_url=member.creator_profile_url,
            display_name=member.display_name,
            platform_context=member.platform_context_json,
            enabled=member.enabled,
        )
        for member in ProductRepository(db).list_benchmark_members(group_id)
    ]


@router.delete("/benchmark-groups/{group_id}/members/{member_id}", status_code=204)
def delete_benchmark_group_member(
    group_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    _ensure_benchmark_group_writable(db, principal, group)
    member = db.get(BenchmarkGroupMember, member_id)
    if not member or member.benchmark_group_id != group_id:
        raise HTTPException(status_code=404, detail="benchmark group member not found")
    ProductRepository(db).delete_benchmark_member(member)
    db.commit()


@router.patch("/benchmark-groups/{group_id}/members/{member_id}", response_model=BenchmarkGroupMemberRead)
def update_benchmark_group_member(
    group_id: str,
    member_id: str,
    request: BenchmarkGroupMemberUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    _ensure_benchmark_group_writable(db, principal, group)
    member = db.get(BenchmarkGroupMember, member_id)
    if not member or member.benchmark_group_id != group_id:
        raise HTTPException(status_code=404, detail="benchmark group member not found")
    if request.platform is not None:
        member.platform = _enum_value(request.platform)
    if request.creator_platform_id is not None:
        member.creator_platform_id = request.creator_platform_id
    if request.creator_profile_url is not None:
        member.creator_profile_url = request.creator_profile_url
    if request.display_name is not None:
        member.display_name = request.display_name
    if request.enabled is not None:
        member.enabled = request.enabled
    db.commit()
    db.refresh(member)
    return BenchmarkGroupMemberRead(
        id=member.id,
        benchmark_group_id=member.benchmark_group_id,
        creator_monitor_id=member.creator_monitor_id,
        platform=member.platform,
        creator_platform_id=member.creator_platform_id,
        creator_profile_url=member.creator_profile_url,
        display_name=member.display_name,
        platform_context=member.platform_context_json,
        enabled=member.enabled,
    )


@router.post("/benchmark-groups/{group_id}/business-account-types")
def bind_benchmark_group_business_type(
    group_id: str,
    request: BindBenchmarkGroupRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    _ensure_benchmark_group_writable(db, principal, group)
    if not db.get(BusinessAccountType, request.business_account_type_id):
        raise HTTPException(status_code=404, detail="business account type not found")
    binding = ProductRepository(db).bind_business_type_to_benchmark_group(business_account_type_id=request.business_account_type_id, benchmark_group_id=group_id)
    db.commit()
    return {"binding_id": binding.id}


@router.get("/benchmark-groups/{group_id}/business-account-types", response_model=list[BenchmarkGroupBusinessAccountTypeRead])
def list_benchmark_group_business_types(
    group_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    group = db.get(BenchmarkGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="benchmark group not found")
    _ensure_benchmark_group_readable(db, principal, group)
    return [
        BenchmarkGroupBusinessAccountTypeRead(
            id=binding.id,
            benchmark_group_id=binding.benchmark_group_id,
            business_account_type_id=binding.business_account_type_id,
            business_account_type_name=business_type.name if business_type else None,
        )
        for binding, business_type in ProductRepository(db).list_business_types_for_benchmark_group(group_id)
    ]


def _filtered_templates(db: Session, principal: Principal) -> list[TaskTemplate]:
    visible = list_visible_business_type_ids(db, principal)
    if visible is None:
        return ProductRepository(db).list_task_templates()
    if not visible:
        return []
    return ProductRepository(db).list_task_templates(business_account_type_ids=list(visible))


@router.post("/task-templates", response_model=TaskTemplateRead)
def create_task_template(
    request: TaskTemplateCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    if not request.business_account_type_id:
        raise HTTPException(status_code=400, detail="business_account_type_id is required")
    ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    service = TaskMaterializationService(db)
    config = service.validate_template_config(_enum_value(request.template_type), request.config)
    template = ProductRepository(db).create_task_template(
        name=request.name,
        template_type=_enum_value(request.template_type),
        platform=_enum_value(request.platform) if request.platform else None,
        business_account_type_id=request.business_account_type_id,
        created_by_user_id=principal.user_id,
        config=config,
        enabled=request.enabled,
    )
    db.commit()
    return _task_template_read(service, template)


@router.get("/task-templates", response_model=list[TaskTemplateRead])
def list_task_templates(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    service = TaskMaterializationService(db)
    return [_task_template_read(service, item) for item in _filtered_templates(db, principal)]


@router.get("/task-templates/list", response_model=list[TaskTemplateListItem])
def list_task_template_items(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    return [_task_template_list_item(db, principal, item) for item in _filtered_templates(db, principal)]


@router.get("/task-templates/{template_id}", response_model=TaskTemplateRead)
def get_task_template(
    template_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    db.commit()
    return _task_template_read(TaskMaterializationService(db), template)


@router.delete("/task-templates/{template_id}", status_code=204)
def delete_task_template(
    template_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    ensure_template_deletable(principal, template)
    ProductRepository(db).delete_task_template(template)
    db.commit()


@router.get("/task-templates/{template_id}/readiness", response_model=TaskTemplateReadiness)
def get_task_template_readiness(
    template_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    db.commit()
    return _template_readiness(TaskMaterializationService(db), template)


@router.get("/task-templates/{template_id}/run-readiness", response_model=TaskTemplateReadiness)
def get_task_template_run_readiness(
    template_id: str,
    executor_account_id: str = Query(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    ensure_executor_account_for_template(db, principal, template, executor_account_id)
    db.commit()
    return _run_readiness(TaskMaterializationService(db), template, executor_account_id)


@router.post("/task-templates/recommendation-feed", response_model=TaskTemplateRead)
def create_recommendation_feed_task_template(
    request: RecommendationFeedTaskTemplateCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    payload = request.model_dump(mode="json", exclude={"name", "enabled", "business_account_type_id"})
    template = _create_typed_task_template(
        db,
        name=request.name,
        enabled=request.enabled,
        template_type="recommendation_feed_task",
        business_account_type_id=request.business_account_type_id,
        created_by_user_id=principal.user_id,
        payload=payload,
        platform=Platform.XHS.value,
    )
    db.commit()
    return _task_template_read(TaskMaterializationService(db), template)


@router.patch("/task-templates/recommendation-feed/{template_id}", response_model=TaskTemplateRead)
def update_recommendation_feed_task_template(
    template_id: str,
    request: RecommendationFeedTaskTemplateUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template or template.template_type != "recommendation_feed_task":
        raise HTTPException(status_code=404, detail="recommendation feed task template not found")
    ensure_template_readable(db, principal, template)
    ensure_template_writable(principal, template)
    if request.business_account_type_id:
        ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    updated = _update_typed_task_template(db, template, request)
    db.commit()
    return _task_template_read(TaskMaterializationService(db), updated)


@router.post("/task-templates/creator-monitor", response_model=TaskTemplateRead)
def create_creator_monitor_task_template(
    request: CreatorMonitorTaskTemplateCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    payload = request.model_dump(mode="json", exclude={"name", "enabled", "business_account_type_id"})
    template = _create_typed_task_template(
        db,
        name=request.name,
        enabled=request.enabled,
        template_type="creator_monitor_task",
        business_account_type_id=request.business_account_type_id,
        created_by_user_id=principal.user_id,
        payload=payload,
        platform=Platform.XHS.value,
    )
    db.commit()
    return _task_template_read(TaskMaterializationService(db), template)


@router.patch("/task-templates/creator-monitor/{template_id}", response_model=TaskTemplateRead)
def update_creator_monitor_task_template(
    template_id: str,
    request: CreatorMonitorTaskTemplateUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template or template.template_type != "creator_monitor_task":
        raise HTTPException(status_code=404, detail="creator monitor task template not found")
    ensure_template_readable(db, principal, template)
    ensure_template_writable(principal, template)
    if request.business_account_type_id:
        ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    updated = _update_typed_task_template(db, template, request)
    db.commit()
    return _task_template_read(TaskMaterializationService(db), updated)


@router.post("/task-templates/keyword-search", response_model=TaskTemplateRead)
def create_keyword_search_task_template(
    request: KeywordSearchTaskTemplateCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    payload = request.model_dump(mode="json", exclude={"name", "enabled", "business_account_type_id"})
    template = _create_typed_task_template(
        db,
        name=request.name,
        enabled=request.enabled,
        template_type="keyword_search_task",
        business_account_type_id=request.business_account_type_id,
        created_by_user_id=principal.user_id,
        payload=payload,
        platform=_enum_value(request.platform),
    )
    db.commit()
    return _task_template_read(TaskMaterializationService(db), template)


@router.patch("/task-templates/keyword-search/{template_id}", response_model=TaskTemplateRead)
def update_keyword_search_task_template(
    template_id: str,
    request: KeywordSearchTaskTemplateUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template or template.template_type != "keyword_search_task":
        raise HTTPException(status_code=404, detail="keyword search task template not found")
    ensure_template_readable(db, principal, template)
    ensure_template_writable(principal, template)
    if request.business_account_type_id:
        ensure_business_type_in_scope(db, principal, request.business_account_type_id)
    updated = _update_typed_task_template(db, template, request)
    db.commit()
    return _task_template_read(TaskMaterializationService(db), updated)


@router.post("/task-templates/{template_id}/run", response_model=TaskRunResponse)
def run_task_template(
    template_id: str,
    request: TaskTemplateRunRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    if not template.enabled:
        raise HTTPException(status_code=400, detail="task template disabled")
    ensure_executor_account_for_template(db, principal, template, request.executor_account_id)
    service = TaskMaterializationService(db)
    readiness = _run_readiness(service, template, request.executor_account_id)
    if not readiness.ready:
        raise HTTPException(status_code=409, detail=readiness.model_dump(mode="json"))
    run, job_ids = service.run_template(
        template,
        executor_account_id=request.executor_account_id,
        trigger_type=TaskRunTriggerType.MANUAL,
        requested_by_user_id=principal.user_id,
    )
    jobs = list(db.scalars(select(Job).where(Job.id.in_(job_ids)).order_by(Job.created_at.asc()))) if job_ids else []
    db.commit()
    return TaskRunResponse(
        task_run_id=run.id,
        task_template_id=template.id,
        jobs_created=len(job_ids),
        jobs=[TaskRunCreatedJob(job_id=job.id, job_type=job.job_type, status=job.status) for job in jobs],
        readiness=readiness,
    )


@router.get("/task-runs", response_model=TaskRunListResponse)
def list_task_runs(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    service = TaskMaterializationService(db)
    runs = list(db.scalars(select(TaskRun).order_by(TaskRun.created_at.desc()).limit(50)))
    items = [_task_run_read(service, run, include_jobs=False) for run in runs]
    db.commit()
    return TaskRunListResponse(items=items)


@router.get("/task-runs/{task_run_id}", response_model=TaskRunRead)
def get_task_run(
    task_run_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    run = db.get(TaskRun, task_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="task run not found")
    template = db.get(TaskTemplate, run.task_template_id) if run.task_template_id else None
    if template:
        ensure_template_readable(db, principal, template)
    service = TaskMaterializationService(db)
    body = _task_run_read(service, run)
    db.commit()
    return body


@router.get("/task-templates/{template_id}/runs", response_model=TaskRunListResponse)
def list_template_runs(
    template_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    service = TaskMaterializationService(db)
    runs = list(
        db.scalars(
            select(TaskRun)
            .where(TaskRun.task_template_id == template_id)
            .order_by(TaskRun.created_at.desc())
            .limit(5)
        )
    )
    items = [_task_run_read(service, run, include_jobs=False) for run in runs]
    db.commit()
    return TaskRunListResponse(items=items)


@router.get("/task-templates/{template_id}/schedules", response_model=list[TaskScheduleRead])
def list_template_schedules(
    template_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    items = ProductRepository(db).list_task_schedules(task_template_id=template_id)
    if _is_operator(principal):
        items = [item for item in items if item.created_by_user_id == principal.user_id]
    return [_schedule_read(item) for item in items]


@router.post("/task-schedules", response_model=TaskScheduleRead)
def create_task_schedule(
    request: TaskScheduleCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    template = db.get(TaskTemplate, request.task_template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    ensure_template_schedule_creatable(principal, template)
    ensure_executor_account_for_template(db, principal, template, request.executor_account_id)
    schedule = ProductRepository(db).create_task_schedule(
        task_template_id=request.task_template_id,
        executor_account_id=request.executor_account_id,
        created_by_user_id=principal.user_id,
        schedule_type=_enum_value(request.schedule_type),
        interval_seconds=request.interval_seconds,
        daily_time_window=request.daily_time_window,
        enabled=request.enabled,
        next_run_at=request.next_run_at,
    )
    db.commit()
    return _schedule_read(schedule)


@router.patch("/task-schedules/{schedule_id}", response_model=TaskScheduleRead)
def update_task_schedule(
    schedule_id: str,
    request: TaskScheduleUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    schedule = db.get(TaskSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="task schedule not found")
    ensure_schedule_writable(principal, schedule)
    template = db.get(TaskTemplate, schedule.task_template_id)
    if not template:
        raise HTTPException(status_code=404, detail="task template not found")
    ensure_template_readable(db, principal, template)
    patch = request.model_dump(exclude_unset=True)
    if "executor_account_id" in patch and patch["executor_account_id"]:
        ensure_executor_account_for_template(db, principal, template, patch["executor_account_id"])
        schedule.executor_account_id = patch["executor_account_id"]
    if "schedule_type" in patch and patch["schedule_type"] is not None:
        schedule.schedule_type = _enum_value(patch["schedule_type"])
    if "interval_seconds" in patch:
        schedule.interval_seconds = patch["interval_seconds"]
    if "daily_time_window" in patch and patch["daily_time_window"] is not None:
        schedule.daily_time_window_json = patch["daily_time_window"]
    if "enabled" in patch and patch["enabled"] is not None:
        schedule.enabled = patch["enabled"]
    if "next_run_at" in patch:
        schedule.next_run_at = patch["next_run_at"]
    db.commit()
    return _schedule_read(schedule)


@router.get("/task-schedules", response_model=list[TaskScheduleRead])
def list_task_schedules(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*_TASK_TEMPLATE_READ_ROLES)),
):
    if _is_operator(principal):
        items = ProductRepository(db).list_task_schedules(created_by_user_id=principal.user_id)
    else:
        items = ProductRepository(db).list_task_schedules()
    return [_schedule_read(item) for item in items]


@router.post("/task-schedules/materialize-due")
def materialize_due_task_schedules(db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    results = TaskMaterializationService(db).materialize_due_schedules()
    db.commit()
    return {"materialized": results, "schedule_count": len(results), "job_count": sum(len(item["job_ids"]) for item in results)}


@router.post("/behavior-profiles", response_model=BehaviorProfileRead)
def create_behavior_profile(request: BehaviorProfileCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    item = ProductRepository(db).create_behavior_profile(name=request.name, description=request.description, enabled=request.enabled, config=request.config)
    db.commit()
    return BehaviorProfileRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled, config=item.config_json)


@router.get("/behavior-profiles", response_model=list[BehaviorProfileRead])
def list_behavior_profiles(
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    return [
        BehaviorProfileRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled, config=item.config_json or {})
        for item in ProductRepository(db).list_behavior_profiles()
    ]


@router.post("/network-egress-profiles", response_model=NetworkEgressProfileRead)
def create_network_egress_profile(request: NetworkEgressProfileCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    item = ProductRepository(db).create_network_egress_profile(name=request.name, strategy=_enum_value(request.strategy), description=request.description, enabled=request.enabled, config=request.config)
    db.commit()
    return NetworkEgressProfileRead(id=item.id, name=item.name, strategy=item.strategy, description=item.description, enabled=item.enabled, config=item.config_json)


@router.get("/network-egress-profiles", response_model=list[NetworkEgressProfileRead])
def list_network_egress_profiles(
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    return [
        NetworkEgressProfileRead(id=item.id, name=item.name, strategy=item.strategy, description=item.description, enabled=item.enabled, config=item.config_json or {})
        for item in ProductRepository(db).list_network_egress_profiles()
    ]


@router.post("/risk-policies", response_model=RiskPolicyRead)
def create_risk_policy(request: RiskPolicyCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    item = ProductRepository(db).create_risk_policy(
        name=request.name,
        description=request.description,
        enabled=request.enabled,
        behavior_profile_id=request.behavior_profile_id,
        network_egress_profile_id=request.network_egress_profile_id,
        config=request.config,
    )
    db.commit()
    return RiskPolicyRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled, behavior_profile_id=item.behavior_profile_id, network_egress_profile_id=item.network_egress_profile_id, config=item.config_json)


@router.get("/risk-policies", response_model=list[RiskPolicyRead])
def list_risk_policies(
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    return [
        RiskPolicyRead(id=item.id, name=item.name, description=item.description, enabled=item.enabled, behavior_profile_id=item.behavior_profile_id, network_egress_profile_id=item.network_egress_profile_id, config=item.config_json or {})
        for item in ProductRepository(db).list_risk_policies()
    ]


@router.post("/business-account-types/{business_account_type_id}/rule-sets", response_model=BusinessAccountTypeRuleSetRead)
def bind_business_account_type_rule_set(business_account_type_id: str, request: BusinessAccountTypeRuleSetBindRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    if not db.get(BusinessAccountType, business_account_type_id):
        raise HTTPException(status_code=404, detail="business account type not found")
    rule_set = db.get(KeywordRuleSet, request.rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="rule set not found")
    binding = ProductRepository(db).bind_rule_set_to_business_type(
        business_account_type_id=business_account_type_id,
        rule_set_id=request.rule_set_id,
        is_default=request.is_default,
    )
    db.commit()
    return BusinessAccountTypeRuleSetRead(id=binding.id, business_account_type_id=binding.business_account_type_id, rule_set_id=binding.rule_set_id, rule_set_name=rule_set.name, is_default=binding.is_default)


@router.get("/business-account-types/{business_account_type_id}/rule-sets", response_model=list[BusinessAccountTypeRuleSetRead])
def list_business_account_type_rule_sets(
    business_account_type_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    if not db.get(BusinessAccountType, business_account_type_id):
        raise HTTPException(status_code=404, detail="business account type not found")
    ensure_business_type_in_scope(db, principal, business_account_type_id)
    return [
        BusinessAccountTypeRuleSetRead(
            id=binding.id,
            business_account_type_id=binding.business_account_type_id,
            rule_set_id=binding.rule_set_id,
            rule_set_name=rule_set.name if rule_set else None,
            is_default=binding.is_default,
        )
        for binding, rule_set in ProductRepository(db).list_rule_sets_for_business_type(business_account_type_id)
    ]


@router.get(
    "/business-account-types/{business_account_type_id}/benchmark-groups",
    response_model=list[BusinessAccountTypeBenchmarkGroupRead],
)
def list_business_account_type_benchmark_groups(
    business_account_type_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    if not db.get(BusinessAccountType, business_account_type_id):
        raise HTTPException(status_code=404, detail="business account type not found")
    ensure_business_type_in_scope(db, principal, business_account_type_id)
    return [
        BusinessAccountTypeBenchmarkGroupRead(
            id=binding.id,
            business_account_type_id=binding.business_account_type_id,
            benchmark_group_id=binding.benchmark_group_id,
            benchmark_group_name=group.name if group else None,
        )
        for binding, group in ProductRepository(db).list_benchmark_groups_for_business_type(business_account_type_id)
    ]


@router.get("/keyword-rule-sets", response_model=list[KeywordRuleSetRead])
def list_keyword_rule_sets(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    rows = ProductRepository(db).list_keyword_rule_sets()
    if _is_operator(principal):
        business_type_ids = _operator_business_type_ids(db, principal)
        if not business_type_ids:
            return []
        allowed_rule_set_ids = set(
            db.scalars(
                select(BusinessAccountTypeRuleSet.rule_set_id).where(
                    BusinessAccountTypeRuleSet.business_account_type_id.in_(list(business_type_ids))
                )
            )
        )
        rows = [row for row in rows if row.id in allowed_rule_set_ids]
    return [_keyword_rule_set_read(db, row) for row in rows]


@router.post("/keyword-rule-sets", response_model=KeywordRuleSetRead)
def create_keyword_rule_set(
    request: KeywordRuleSetCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    created_by_user_id = principal.user_id
    created_by_employee_id = None
    auto_bind_business_types: set[str] = set()
    if _is_operator(principal):
        created_by_employee_id, auto_bind_business_types = _ensure_operator_has_business_types(db, principal)
    row = ProductRepository(db).create_keyword_rule_set(
        name=request.name,
        rule_scope=request.rule_scope,
        enabled=request.enabled,
        config=request.config,
        created_by_user_id=created_by_user_id,
        created_by_employee_id=created_by_employee_id,
    )
    if _is_operator(principal):
        for business_type_id in auto_bind_business_types:
            ProductRepository(db).bind_rule_set_to_business_type(
                business_account_type_id=business_type_id,
                rule_set_id=row.id,
                is_default=False,
            )
    db.commit()
    return _keyword_rule_set_read(db, row)


@router.patch("/keyword-rule-sets/{rule_set_id}", response_model=KeywordRuleSetRead)
def update_keyword_rule_set(
    rule_set_id: str,
    request: KeywordRuleSetUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    row = db.get(KeywordRuleSet, rule_set_id)
    if not row:
        raise HTTPException(status_code=404, detail="rule set not found")
    _ensure_rule_set_readable(db, principal, row)
    _ensure_rule_set_writable(db, principal, row)
    row = ProductRepository(db).update_keyword_rule_set(row, **request.model_dump(exclude_unset=True))
    db.commit()
    return _keyword_rule_set_read(db, row)


@router.delete("/keyword-rule-sets/{rule_set_id}", status_code=204)
def delete_keyword_rule_set(
    rule_set_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    row = db.get(KeywordRuleSet, rule_set_id)
    if not row:
        raise HTTPException(status_code=404, detail="rule set not found")
    _ensure_rule_set_readable(db, principal, row)
    _ensure_rule_set_writable(db, principal, row)
    ProductRepository(db).delete_keyword_rule_set(row)
    db.commit()


@router.get("/keyword-rule-sets/{rule_set_id}/rules", response_model=list[KeywordRuleRead])
def list_keyword_rules(
    rule_set_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    rule_set = db.get(KeywordRuleSet, rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="rule set not found")
    _ensure_rule_set_readable(db, principal, rule_set)
    return [
        KeywordRuleRead(id=row.id, rule_set_id=row.rule_set_id, keyword=row.keyword, normalized_keyword=row.normalized_keyword, match_mode=row.match_mode, enabled=row.enabled, weight=row.weight)
        for row in ProductRepository(db).list_keyword_rules(rule_set_id)
    ]


@router.post("/keyword-rule-sets/{rule_set_id}/rules", response_model=KeywordRuleRead)
def create_keyword_rule(
    rule_set_id: str,
    request: KeywordRuleCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    rule_set = db.get(KeywordRuleSet, rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="rule set not found")
    _ensure_rule_set_readable(db, principal, rule_set)
    _ensure_rule_set_writable(db, principal, rule_set)
    row = ProductRepository(db).create_keyword_rule(rule_set_id=rule_set_id, keyword=request.keyword, normalized_keyword=request.normalized_keyword, match_mode=request.match_mode, enabled=request.enabled, weight=request.weight)
    db.commit()
    return KeywordRuleRead(id=row.id, rule_set_id=row.rule_set_id, keyword=row.keyword, normalized_keyword=row.normalized_keyword, match_mode=row.match_mode, enabled=row.enabled, weight=row.weight)


@router.patch("/keyword-rules/{rule_id}", response_model=KeywordRuleRead)
def update_keyword_rule(
    rule_id: str,
    request: KeywordRuleUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    row = db.get(KeywordRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="rule not found")
    rule_set = db.get(KeywordRuleSet, row.rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="rule set not found")
    _ensure_rule_set_readable(db, principal, rule_set)
    _ensure_rule_set_writable(db, principal, rule_set)
    row = ProductRepository(db).update_keyword_rule(row, **request.model_dump(exclude_unset=True))
    db.commit()
    return KeywordRuleRead(id=row.id, rule_set_id=row.rule_set_id, keyword=row.keyword, normalized_keyword=row.normalized_keyword, match_mode=row.match_mode, enabled=row.enabled, weight=row.weight)


@router.delete("/keyword-rules/{rule_id}", status_code=204)
def delete_keyword_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    row = db.get(KeywordRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="rule not found")
    rule_set = db.get(KeywordRuleSet, row.rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="rule set not found")
    _ensure_rule_set_readable(db, principal, rule_set)
    _ensure_rule_set_writable(db, principal, rule_set)
    ProductRepository(db).delete_keyword_rule(row)
    db.commit()


@router.get("/product/options", response_model=ProductOptions)
def get_product_options():
    return _product_options()


@router.get("/product/options/roles")
def get_role_options():
    return _product_options().roles


@router.get("/product/options/platforms")
def get_platform_options():
    return _product_options().platforms


@router.get("/product/options/feed-types")
def get_feed_type_options():
    return _product_options().feed_types


@router.get("/product/options/task-template-types")
def get_task_template_type_options():
    return _product_options().task_template_types


@router.get("/product/options/workflow-statuses")
def get_workflow_status_options():
    return _product_options().workflow_statuses


@router.get("/product/options/candidate-buckets")
def get_candidate_bucket_options():
    return _product_options().candidate_buckets


def _split_enum_filter(raw: str | None, enum_cls) -> list[str] | None:
    if not raw:
        return None
    allowed = {item.value for item in enum_cls}
    values = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid filter value: {', '.join(invalid)}")
    return values or None


@router.get("/product/options/account-statuses")
def get_account_status_options():
    return _product_options().account_statuses


@router.get("/product/options/agent-statuses")
def get_agent_status_options():
    return _product_options().agent_statuses


@router.get("/intelligence/contents/product", response_model=IntelligenceContentProductList)
def list_product_intelligence_contents(
    platform: Platform | None = None,
    source_surface: SourceSurface | None = None,
    candidate_bucket: str | None = Query(default=None),
    workflow_status: str | None = Query(default=None),
    assigned_to_user_id: str | None = None,
    business_keyword: str | None = None,
    content_query: str | None = None,
    search_keyword: str | None = None,
    discovered_after: datetime | None = None,
    discovered_before: datetime | None = None,
    data_status: ContentDataStatus | None = None,
    tag: str | None = None,
    platform_tag: str | None = None,
    manual_tag: str | None = None,
    manual_tag_id: str | None = None,
    untagged: bool | None = None,
    search_sort: str | None = None,
    note_type_filter: str | None = None,
    publish_time_filter: str | None = None,
    min_like_count: int | None = None,
    min_comment_count: int | None = None,
    min_collect_count: int | None = None,
    in_reference_library: bool | None = None,
    reference_library_type: str | None = None,
    selection_source: str | None = None,
    reference_rating: str | None = None,
    sort_by: str = "latest_discovered_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    candidate_bucket_values = _split_enum_filter(candidate_bucket, CandidateBucket)
    workflow_status_values = _split_enum_filter(workflow_status, ContentWorkflowStatus)
    operator_scope = resolve_operator_intelligence_list_scope(db, principal, assigned_to_user_id)
    list_assigned_to_user_id = operator_scope.assigned_to_user_id if operator_scope else assigned_to_user_id
    list_discovered_by_account_ids = (
        list(operator_scope.discovered_by_account_ids) if operator_scope else None
    )
    items, total = WorkflowRepository(db).list_intelligence_contents(
        page=page,
        page_size=page_size,
        platform=_enum_value(platform) if platform else None,
        source_surface=_enum_value(source_surface) if source_surface else None,
        candidate_buckets=candidate_bucket_values,
        workflow_statuses=workflow_status_values,
        assigned_to_user_id=list_assigned_to_user_id,
        discovered_by_account_ids=list_discovered_by_account_ids,
        business_keyword=business_keyword,
        content_query=content_query,
        search_keyword=search_keyword,
        discovered_after=discovered_after,
        discovered_before=discovered_before,
        data_status=_enum_value(data_status) if data_status else None,
        tag=tag,
        platform_tag=platform_tag,
        manual_tag=manual_tag,
        manual_tag_id=manual_tag_id,
        untagged=untagged,
        search_sort=search_sort,
        note_type_filter=note_type_filter,
        publish_time_filter=publish_time_filter,
        min_like_count=min_like_count,
        min_comment_count=min_comment_count,
        min_collect_count=min_collect_count,
        in_reference_library=in_reference_library,
        reference_library_type=reference_library_type,
        selection_source=selection_source,
        reference_rating=reference_rating,
        sort_by=sort_by,
        sort_order=sort_order,
        pool_only=True,
    )
    db.commit()
    return IntelligenceContentProductList(items=items, page=page, page_size=page_size, total=total)


@router.get("/intelligence/contents/{content_id}/product-detail", response_model=IntelligenceContentProductDetail)
def get_intelligence_content_product_detail(content_id: str, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES))):
    content = _ensure_content(content_id, db)
    repo = WorkflowRepository(db)
    state = repo.ensure_state(content_id)
    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content.latest_snapshot_id else None
    comments = list(
        db.scalars(
            select(CommentSnapshot)
            .where(CommentSnapshot.content_id == content_id)
            .order_by(CommentSnapshot.created_time.desc().nullslast(), CommentSnapshot.fetched_at.desc())
            .limit(20)
        )
    )
    decision = repo.latest_decision_for_content(content_id)
    notes = repo.list_notes(content_id=content_id)
    assignments = repo.assignment_history(content_id)
    discoveries = repo.discovery_events(content_id)
    discovery_meta_rows = [item.discovery_meta_json for item in discoveries if item.discovery_meta_json]
    metadata = content.metadata_json or {}
    summary = repo._discovery_summary(content_id)
    comment_count = summary.get("comment_snapshot_count") or 0
    enrichment_flags = metadata.get("enrichment_flags") if isinstance(metadata.get("enrichment_flags"), dict) else {}
    data_status_value = derive_data_status(
        latest_snapshot_id=content.latest_snapshot_id,
        comment_snapshot_count=comment_count,
        detail_fetch_failed=bool(enrichment_flags.get("detail_failed")),
        comment_fetch_failed=bool(enrichment_flags.get("comment_failed")),
    )
    ref_items = ReferenceLibraryRepository(db).list_for_content(content_id)
    active_jobs = list(
        db.scalars(
            select(Job).where(
                Job.job_type.in_([JobType.DETAIL_FETCH.value, JobType.COMMENT_FETCH.value]),
                Job.status.in_([JobStatus.PENDING.value, JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            )
        )
    )
    pending_detail_job = next((job.id for job in active_jobs if job.job_type == JobType.DETAIL_FETCH.value and (job.payload_json or {}).get("content_id") == content_id), None)
    pending_comment_job = next((job.id for job in active_jobs if job.job_type == JobType.COMMENT_FETCH.value and (job.payload_json or {}).get("content_id") == content_id), None)
    media = MediaService()
    db.commit()
    return IntelligenceContentProductDetail(
        identity=ContentIdentityDetail(
            id=content.id,
            platform=content.platform,
            platform_content_id=content.platform_content_id,
            canonical_url=content.canonical_url,
            content_type=content.content_type,
            first_seen_at=content.first_seen_at,
            last_seen_at=content.last_seen_at,
            metadata=content.metadata_json or {},
        ),
        latest_snapshot=(
            ContentSnapshotDetail(
                id=snapshot.id,
                title=snapshot.title,
                body_text=snapshot.body_text,
                author_platform_id=snapshot.author_platform_id,
                author_name=snapshot.author_name,
                author_avatar_url=snapshot.author_avatar_url,
                cover_url=snapshot.cover_url,
                cover_display_url=media.build_cover_display_url_for_snapshot(content_id, snapshot, content.metadata_json or {}),
                image_urls=snapshot.image_urls_json or [],
                video_url=snapshot.video_url,
                like_count=snapshot.like_count,
                comment_count=snapshot.comment_count,
                collect_count=snapshot.collect_count,
                share_count=snapshot.share_count,
                publish_time=snapshot.publish_time,
                fetched_at=snapshot.fetched_at,
            )
            if snapshot
            else None
        ),
        comments=[
            CommentSnapshotDetail(
                id=comment.id,
                platform_comment_id=comment.platform_comment_id,
                parent_platform_comment_id=comment.parent_platform_comment_id,
                author_platform_id=comment.author_platform_id,
                author_name=comment.author_name,
                body_text=comment.body_text,
                like_count=comment.like_count,
                created_time=comment.created_time,
                fetched_at=comment.fetched_at,
            )
            for comment in comments
        ],
        latest_candidate_decision=(
            CandidateDecisionDetail(
                id=decision.id,
                candidate_bucket=decision.candidate_bucket,
                business_keyword_hits=decision.business_keyword_hits_json or [],
                lead_keyword_hits=decision.lead_keyword_hits_json or [],
                comment_keyword_hits=decision.comment_keyword_hits_json or [],
                decision_reason=decision.decision_reason_json or {},
                evaluated_at=decision.evaluated_at,
            )
            if decision
            else None
        ),
        workflow_state=_workflow_read(state),
        notes=[ContentOperatorNoteRead(id=note.id, content_id=note.content_id, user_id=note.user_id, note=note.note, created_at=note.created_at) for note in notes],
        assignment_history=[
            AssignmentHistoryItem(id=item.id, assigned_to_user_id=item.assigned_to_user_id, assigned_by_user_id=item.assigned_by_user_id, assigned_at=item.assigned_at, status=item.status, remark=item.remark)
            for item in assignments
        ],
        discovery_events_summary=[
            DiscoveryEventSummaryItem(
                id=item.id,
                source_surface=item.source_surface,
                feed_type=item.feed_type,
                feed_position=item.feed_position,
                discovered_at=item.discovered_at,
                account_id=item.account_id,
                job_id=item.job_id,
                search_keyword=(item.discovery_meta_json or {}).get("search_keyword"),
                search_keywords=(item.discovery_meta_json or {}).get("search_keywords") or [],
            )
            for item in discoveries
        ],
        reference_library_items=[
            ReferenceLibraryItemRead(**ReferenceLibraryRepository(db)._item_dict(item, content, snapshot))
            for item in ref_items
        ],
        platform_tags=extract_platform_tags(metadata, snapshot.raw_payload_json if snapshot else None),
        search_tags=extract_search_tags(metadata, discovery_meta_rows),
        manual_tags=ManualTagRepository(db).list_content_tag_names(content_id) or extract_manual_tags(metadata),
        data_status=data_status_value,
        pending_detail_job_id=pending_detail_job,
        pending_comment_job_id=pending_comment_job,
    )


@router.post("/intelligence/contents/{content_id}/assign", response_model=ContentWorkflowRead)
def assign_intelligence_content(content_id: str, request: ContentAssignRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    if not db.get(ContentIdentity, content_id):
        raise HTTPException(status_code=404, detail="content not found")
    state = WorkflowRepository(db).assign(
        content_id=content_id,
        assigned_to_user_id=request.assigned_to_user_id,
        assigned_by_user_id=request.assigned_by_user_id,
        remark=request.remark,
    )
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/{content_id}/select", response_model=ContentWorkflowRead)
def select_intelligence_content(content_id: str, request: ContentStatusActionRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    state = WorkflowRepository(db).set_status(content_id=content_id, status=ContentWorkflowStatus.SELECTED, user_id=request.user_id, note=request.note)
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/{content_id}/discard", response_model=ContentWorkflowRead)
def discard_intelligence_content(content_id: str, request: ContentStatusActionRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    state = WorkflowRepository(db).set_status(content_id=content_id, status=ContentWorkflowStatus.DISCARDED, user_id=request.user_id, note=request.note)
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/{content_id}/archive", response_model=ContentWorkflowRead)
def archive_intelligence_content(content_id: str, request: ContentStatusActionRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    state = WorkflowRepository(db).set_status(content_id=content_id, status=ContentWorkflowStatus.ARCHIVED, user_id=request.user_id, note=request.note)
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/bulk-status", response_model=ContentBulkStatusResponse)
def bulk_set_intelligence_content_status(
    request: ContentBulkStatusRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    if len(request.content_ids) > 100:
        raise HTTPException(status_code=400, detail="bulk content limit exceeded")
    status_by_action = {
        "select": ContentWorkflowStatus.SELECTED,
        "discard": ContentWorkflowStatus.DISCARDED,
        "archive": ContentWorkflowStatus.ARCHIVED,
    }
    status = status_by_action.get(request.action)
    if not status:
        raise HTTPException(status_code=400, detail="unsupported bulk status action")

    repo = WorkflowRepository(db)
    succeeded: list[ContentWorkflowRead] = []
    failed: list[ContentBulkStatusFailure] = []
    actor_id = request.user_id or principal.user_id

    for content_id in request.content_ids:
        if not db.get(ContentIdentity, content_id):
            failed.append(ContentBulkStatusFailure(content_id=content_id, code="not_found", message="content not found"))
            continue
        try:
            state = repo.set_status(content_id=content_id, status=status, user_id=actor_id, note=request.note)
            succeeded.append(_workflow_read(state))
        except Exception as exc:
            failed.append(ContentBulkStatusFailure(content_id=content_id, code="update_failed", message=str(exc)))

    db.commit()
    return ContentBulkStatusResponse(succeeded=succeeded, failed=failed)


@router.post("/intelligence/contents/{content_id}/notes", response_model=ContentOperatorNoteRead)
def add_intelligence_content_note(content_id: str, request: ContentNoteCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    if not db.get(ContentIdentity, content_id):
        raise HTTPException(status_code=404, detail="content not found")
    note = WorkflowRepository(db).add_note(content_id=content_id, user_id=request.user_id, note=request.note)
    db.commit()
    return ContentOperatorNoteRead(id=note.id, content_id=note.content_id, user_id=note.user_id, note=note.note, created_at=note.created_at)


@router.get("/intelligence/contents/{content_id}/notes", response_model=list[ContentOperatorNoteRead])
def list_intelligence_content_notes(content_id: str, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    return [
        ContentOperatorNoteRead(id=note.id, content_id=note.content_id, user_id=note.user_id, note=note.note, created_at=note.created_at)
        for note in WorkflowRepository(db).list_notes(content_id=content_id)
    ]


@router.patch("/intelligence/contents/{content_id}/manual-tags", response_model=ContentIdentityDetail)
def update_intelligence_manual_tags(content_id: str, request: ManualTagsUpdateRequest, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    service = ManualTagService(db)
    tag_ids = list(request.tag_ids)
    if not tag_ids and request.manual_tags:
        from intelligence_engine.storage.repositories.manual_tag_repository import ManualTagRepository

        repo = ManualTagRepository(db)
        service.ensure_bootstrap()
        for raw_name in request.manual_tags:
            name = repo.normalize_name(raw_name)
            if not name:
                continue
            tag = repo.get_by_name(name)
            if not tag:
                tag = repo.create_tag(name=name, created_by_user_id=request.user_id or principal.user_id)
            tag_ids.append(tag.id)
    try:
        content = service.set_content_tags(
            content_id=content_id,
            tag_ids=tag_ids,
            principal=principal,
            user_id=request.user_id or principal.user_id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="content not found")
    except ManualTagActionError as error:
        raise HTTPException(status_code=400, detail={"code": error.code, "message": error.message})
    db.commit()
    return ContentIdentityDetail(
        id=content.id,
        platform=content.platform,
        platform_content_id=content.platform_content_id,
        canonical_url=content.canonical_url,
        content_type=content.content_type,
        first_seen_at=content.first_seen_at,
        last_seen_at=content.last_seen_at,
        metadata=content.metadata_json or {},
    )


@router.post("/intelligence/contents/{content_id}/enqueue-detail-fetch", response_model=EnqueueFetchResponse)
def enqueue_intelligence_detail_fetch(content_id: str, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    repo = ContentRepository(db)
    try:
        account_id = _manual_fetch_account_id(db, repo, content_id=content_id, principal=principal)
        run = _create_manual_fetch_task_run(db, account_id=account_id, requested_by_user_id=principal.user_id)
        job = repo.enqueue_detail_fetch(content_id=content_id, account_id=account_id, task_run_id=run.id)
        TaskMaterializationService(db).refresh_task_run(run)
    except ValueError:
        raise HTTPException(status_code=404, detail="content not found")
    db.commit()
    return EnqueueFetchResponse(job_id=job.id, job_type=job.job_type, status=job.status)


@router.post("/intelligence/contents/{content_id}/enqueue-comment-fetch", response_model=EnqueueFetchResponse)
def enqueue_intelligence_comment_fetch(content_id: str, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    repo = ContentRepository(db)
    try:
        account_id = _manual_fetch_account_id(db, repo, content_id=content_id, principal=principal)
        run = _create_manual_fetch_task_run(db, account_id=account_id, requested_by_user_id=principal.user_id)
        job = repo.enqueue_comment_fetch(content_id=content_id, account_id=account_id, task_run_id=run.id)
        TaskMaterializationService(db).refresh_task_run(run)
    except ValueError:
        raise HTTPException(status_code=404, detail="content not found")
    db.commit()
    return EnqueueFetchResponse(job_id=job.id, job_type=job.job_type, status=job.status)


@router.post("/intelligence/contents/{content_id}/reference-library-items", response_model=ReferenceLibraryItemRead)
def create_reference_library_item(content_id: str, request: ReferenceLibraryItemCreateRequest, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    content = _ensure_content(content_id, db)
    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content.latest_snapshot_id else None
    repo = ReferenceLibraryRepository(db)
    item = BenchmarkSelectionService(db).manual_select(
        content_id=content_id,
        library_type=_enum_value(request.library_type),
        actor=SelectionActor(
            user_id=request.user_id or principal.user_id,
            employee_id=request.employee_id or get_principal_employee_id(db, principal),
        ),
        selected_reason=request.selected_reason,
        rating=_enum_value(request.rating) if request.rating else None,
        manual_tags=request.manual_tags,
        material_tags=request.material_tags,
        usage_status=_enum_value(request.usage_status),
        note=request.note,
        metadata=request.metadata,
        matched_keywords=request.matched_keywords,
        selection_sources=request.selection_sources,
    )
    db.commit()
    return ReferenceLibraryItemRead(**repo._item_dict(item, content, snapshot))


@router.get("/reference-library/items", response_model=ReferenceLibraryItemList)
def list_reference_library_items(
    library_type: str | None = None,
    platform: str | None = None,
    selection_source: str | None = None,
    rating: str | None = None,
    usage_status: str | None = None,
    sort_by: str = "selected_at",
    sort_order: str = "desc",
    search_keyword: str | None = None,
    content_query: str | None = None,
    manual_tag_id: str | None = None,
    untagged: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    items, total = ReferenceLibraryRepository(db).list_items(
        page=page,
        page_size=page_size,
        library_type=library_type,
        platform=platform,
        selection_source=selection_source,
        rating=rating,
        usage_status=usage_status,
        search_keyword=search_keyword,
        content_query=content_query,
        manual_tag_id=manual_tag_id,
        untagged=untagged,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    db.commit()
    return ReferenceLibraryItemList(items=items, page=page, page_size=page_size, total=total)


@router.post("/reference-library/items/bulk", response_model=ReferenceLibraryBulkCreateResponse)
def bulk_create_reference_library_items(
    request: ReferenceLibraryBulkCreateRequest,
    atomic: bool = False,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    if len(request.items) > 50:
        raise HTTPException(status_code=400, detail="bulk item limit exceeded")
    if atomic and not principal.has_role(UserRoleName.ADMIN):
        raise HTTPException(status_code=403, detail="atomic bulk requires admin")

    repo = ReferenceLibraryRepository(db)
    service = BenchmarkSelectionService(db)
    succeeded: list[ReferenceLibraryItemRead] = []
    failed: list[ReferenceLibraryBulkCreateFailure] = []
    actor = SelectionActor(user_id=principal.user_id, employee_id=get_principal_employee_id(db, principal))

    for entry in request.items:
        try:
            content = db.get(ContentIdentity, entry.content_id)
            if not content:
                raise ValueError("content not found")
            snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content.latest_snapshot_id else None
            existing = repo.get_active_item(content_id=entry.content_id)
            idempotency_keys = list((existing.metadata_json or {}).get("bulk_idempotency_keys") or []) if existing else []
            if idempotency_key and existing and idempotency_key in idempotency_keys:
                item = existing
            else:
                item = service.manual_select(
                    content_id=entry.content_id,
                    library_type=_enum_value(entry.library_type),
                    actor=actor,
                    selected_reason=entry.selected_reason,
                    rating=_enum_value(entry.rating) if entry.rating else None,
                    manual_tags=entry.manual_tags,
                    material_tags=entry.material_tags,
                    usage_status=_enum_value(entry.usage_status),
                    note=entry.note,
                    metadata=entry.metadata,
                    matched_keywords=entry.matched_keywords,
                    selection_sources=entry.selection_sources,
                )
                if idempotency_key:
                    metadata = dict(item.metadata_json or {})
                    keys = list(metadata.get("bulk_idempotency_keys") or [])
                    if idempotency_key not in keys:
                        metadata["bulk_idempotency_keys"] = [*keys, idempotency_key]
                        item.metadata_json = metadata
                        db.flush()
            succeeded.append(ReferenceLibraryItemRead(**repo._item_dict(item, content, snapshot)))
        except Exception as exc:
            failed.append(
                ReferenceLibraryBulkCreateFailure(
                    content_id=entry.content_id,
                    code="bulk_item_failed",
                    message=str(exc),
                )
            )
            if atomic:
                db.rollback()
                return ReferenceLibraryBulkCreateResponse(succeeded=[], failed=failed)
    db.commit()
    return ReferenceLibraryBulkCreateResponse(succeeded=succeeded, failed=failed)


@router.patch("/reference-library/items/{item_id}", response_model=ReferenceLibraryItemRead)
def update_reference_library_item(item_id: str, request: ReferenceLibraryItemUpdateRequest, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    repo = ReferenceLibraryRepository(db)
    item = repo.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference library item not found")
    content = db.get(ContentIdentity, item.content_id)
    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content and content.latest_snapshot_id else None
    updates = {}
    if request.library_type is not None:
        updates["library_type"] = _enum_value(request.library_type)
    if request.selection_sources is not None:
        updates["selection_sources_json"] = request.selection_sources
    if request.selected_reason is not None:
        updates["selected_reason"] = request.selected_reason
    if request.rating is not None:
        updates["rating"] = _enum_value(request.rating)
    if request.matched_keywords is not None:
        updates["matched_keywords_json"] = request.matched_keywords
    if request.manual_tags is not None:
        updates["manual_tags_json"] = request.manual_tags
    if request.material_tags is not None:
        updates["material_tags_json"] = request.material_tags
    if request.usage_status is not None:
        updates["usage_status"] = _enum_value(request.usage_status)
    if request.note is not None:
        updates["note"] = request.note
    if request.metadata is not None:
        updates["metadata_json"] = request.metadata
    item = repo.update_item(
        item,
        **updates,
        actor_user_id=request.user_id or principal.user_id,
        actor_employee_id=request.employee_id or get_principal_employee_id(db, principal),
    )
    db.commit()
    return ReferenceLibraryItemRead(**repo._item_dict(item, content, snapshot))


@router.post("/reference-library/items/{item_id}/archive", response_model=ReferenceLibraryItemRead)
def archive_reference_library_item(
    item_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ReferenceLibraryRepository(db)
    item = repo.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference library item not found")
    content = db.get(ContentIdentity, item.content_id)
    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content and content.latest_snapshot_id else None
    item = repo.archive_item(item, user_id=principal.user_id, employee_id=get_principal_employee_id(db, principal))
    db.commit()
    return ReferenceLibraryItemRead(**repo._item_dict(item, content, snapshot))


@router.post("/reference-library/items/{item_id}/revoke", response_model=ReferenceLibraryItemRead)
def revoke_reference_library_item(
    item_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.OPERATOR)),
):
    repo = ReferenceLibraryRepository(db)
    item = repo.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="reference library item not found")
    ensure_can_revoke_reference_library_item(principal, item)
    content = db.get(ContentIdentity, item.content_id)
    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content and content.latest_snapshot_id else None
    item = repo.archive_item(
        item,
        user_id=principal.user_id,
        employee_id=get_principal_employee_id(db, principal),
        event_type="revoked",
    )
    db.commit()
    return ReferenceLibraryItemRead(**repo._item_dict(item, content, snapshot))


@router.get("/reference-library/items/{item_id}/events", response_model=list[ReferenceLibraryEventRead])
def list_reference_library_item_events(
    item_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    repo = ReferenceLibraryRepository(db)
    if not repo.get_item(item_id):
        raise HTTPException(status_code=404, detail="reference library item not found")
    limit = max(1, min(limit, 200))
    return [_reference_library_event_read(event) for event in repo.list_events(item_id, limit=limit)]


@router.post("/reference-library/items/re-evaluate", response_model=ReferenceLibraryReevaluateResponse)
def re_evaluate_reference_library_items(
    request: ReferenceLibraryReevaluateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = ReferenceLibraryRepository(db)
    content_ids = list(request.content_ids)
    for item_id in request.item_ids:
        item = repo.get_item(item_id)
        if item and item.content_id not in content_ids:
            content_ids.append(item.content_id)
    service = BenchmarkSelectionService(db)
    results: list[ReferenceLibraryReevaluateResult] = []
    for content_id in content_ids[:50]:
        try:
            item, status, metadata = service.ai_select_by_rules(
                content_id=content_id,
                trigger_source=request.trigger_source,
                actor=SelectionActor(user_id=principal.user_id, employee_id=get_principal_employee_id(db, principal)),
            )
        except ValueError:
            results.append(ReferenceLibraryReevaluateResult(content_id=content_id, status="failed_not_found"))
            continue
        results.append(
            ReferenceLibraryReevaluateResult(
                content_id=content_id,
                item_id=item.id if item else None,
                status=status,
                library_type=item.library_type if item else None,
                rating=item.rating if item else None,
                reason=(metadata or {}).get("ai_reason"),
            )
        )
    db.commit()
    return ReferenceLibraryReevaluateResponse(results=results)


@router.get("/benchmark-rule-profiles", response_model=list[RuleProfileRead])
def list_benchmark_rule_profiles(
    include_disabled: bool = False,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    profiles = RuleProfileService(db).list_profiles(include_disabled=include_disabled)
    db.commit()
    return [_rule_profile_read(profile) for profile in profiles]


@router.put("/benchmark-rule-profiles/{profile_id}", response_model=RuleProfileRead)
def update_benchmark_rule_profile(
    profile_id: str,
    request: RuleProfileUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    service = RuleProfileService(db)
    profile = db.get(RuleProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="rule profile not found")
    profile = service.update_profile(profile, name=request.name, enabled=request.enabled, config=request.config)
    db.commit()
    return _rule_profile_read(profile)


@router.get("/operation-rules", response_model=list[OperationRuleRead])
def list_operation_rules(
    rule_type: str | None = None,
    platform: str | None = None,
    enabled: bool | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    rules = OperationRuleRepository(db).list_rules(
        rule_type=_enum_value(rule_type) if rule_type else None,
        platform=_enum_value(platform) if platform else None,
        enabled=enabled,
        keyword=keyword,
    )
    db.commit()
    return [_operation_rule_read(rule) for rule in rules]


@router.post("/operation-rules", response_model=OperationRuleRead)
def create_operation_rule(
    request: OperationRuleCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    rule = OperationRuleRepository(db).create(
        rule_type=_enum_value(request.rule_type),
        title=request.title,
        content=request.content,
        platform=_enum_value(request.platform) if request.platform else None,
        enabled=request.enabled,
        created_by_user_id=principal.user_id,
    )
    db.commit()
    return _operation_rule_read(rule)


@router.patch("/operation-rules/{rule_id}", response_model=OperationRuleRead)
def update_operation_rule(
    rule_id: str,
    request: OperationRuleUpdateRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = OperationRuleRepository(db)
    rule = repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="operation rule not found")
    rule = repo.update(
        rule,
        title=request.title,
        content=request.content,
        platform=_enum_value(request.platform) if request.platform is not None else None,
        enabled=request.enabled,
        bump_version=request.bump_version,
    )
    db.commit()
    return _operation_rule_read(rule)


@router.delete("/operation-rules/{rule_id}", status_code=204)
def delete_operation_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    repo = OperationRuleRepository(db)
    rule = repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="operation rule not found")
    repo.delete(rule)
    db.commit()


@router.post("/xhs/search-suggestions/tasks", response_model=EnqueueFetchResponse)
def create_xhs_search_suggestion_task(request: XhsSearchSuggestionTaskRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    account = db.get(PlatformAccount, request.executor_account_id)
    if not account:
        raise HTTPException(status_code=404, detail="executor account not found")
    job = JobRepository(db).create_job(
        job_type=JobType.XHS_SEARCH_SUGGEST.value,
        account_id=account.id,
        local_agent_id=None,
        payload={
            "platform": _enum_value(request.platform),
            "executor_account_id": account.id,
            "core_keyword": request.core_keyword,
        },
        priority=110,
    )
    db.commit()
    return EnqueueFetchResponse(job_id=job.id, job_type=job.job_type, status=job.status)


@router.get("/xhs/search-suggestions", response_model=list[XhsSearchSuggestionRead])
def list_xhs_search_suggestions(
    core_keyword: str | None = None,
    platform: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    stmt = select(XhsSearchSuggestion).order_by(XhsSearchSuggestion.fetched_at.desc()).limit(limit)
    if core_keyword:
        stmt = stmt.where(XhsSearchSuggestion.core_keyword == core_keyword)
    if platform:
        stmt = stmt.where(XhsSearchSuggestion.platform == platform)
    rows = list(db.scalars(stmt))
    return [
        XhsSearchSuggestionRead(
            id=row.id,
            platform=row.platform,
            core_keyword=row.core_keyword,
            suggested_keyword=row.suggested_keyword,
            suggestion_rank=row.suggestion_rank,
            source_account_id=row.source_account_id,
            fetched_at=row.fetched_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/intelligence/data-quality/overview", response_model=IntelligenceDataQualityOverview)
def get_intelligence_data_quality_overview(
    window_hours: int = 24,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    overview = build_data_quality_overview(db, window_hours=window_hours)
    db.commit()
    return IntelligenceDataQualityOverview(**overview)
