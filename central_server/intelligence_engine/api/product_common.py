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
    CreativeMaterialPreparationRequest,
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


def _split_enum_filter(raw: str | None, enum_cls) -> list[str] | None:
    if not raw:
        return None
    allowed = {item.value for item in enum_cls}
    values = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid filter value: {', '.join(invalid)}")
    return values or None


__all__ = [name for name in globals() if not name.startswith("__")]
