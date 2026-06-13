from datetime import timedelta

from intelligence_engine.api.product_common import *
from intelligence_engine.db.models import utcnow
from intelligence_engine.domain.enums import TaskScheduleType


router = APIRouter(prefix="/api")


def _default_next_run_at(schedule_type: str, interval_seconds: int | None, next_run_at):
    if next_run_at is not None:
        return next_run_at
    if schedule_type == TaskScheduleType.INTERVAL_SECONDS.value and interval_seconds:
        return utcnow() + timedelta(seconds=interval_seconds)
    return None


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
    account_id = request.account_id or request.config.get("executor_account_id") or request.config.get("account_id")
    business_account_type_id = request.business_account_type_id
    if not business_account_type_id and account_id:
        account = db.get(PlatformAccount, account_id)
        if account:
            business_account_type_id = account.business_account_type_id
    if business_account_type_id:
        ensure_business_type_in_scope(db, principal, business_account_type_id)
    service = TaskMaterializationService(db)
    config = service.validate_template_config(_enum_value(request.template_type), request.config)
    template = ProductRepository(db).create_task_template(
        name=request.name,
        template_type=_enum_value(request.template_type),
        platform=_enum_value(request.platform) if request.platform else None,
        account_id=account_id,
        business_account_type_id=business_account_type_id,
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
    executor_account_id = request.executor_account_id or template.account_id
    if not executor_account_id:
        raise HTTPException(status_code=400, detail="executor_account_id is required")
    ensure_executor_account_for_template(db, principal, template, executor_account_id)
    schedule = ProductRepository(db).create_task_schedule(
        task_template_id=request.task_template_id,
        executor_account_id=executor_account_id,
        created_by_user_id=principal.user_id,
        schedule_type=_enum_value(request.schedule_type),
        interval_seconds=request.interval_seconds,
        daily_time_window=request.daily_time_window,
        enabled=request.enabled,
        next_run_at=_default_next_run_at(_enum_value(request.schedule_type), request.interval_seconds, request.next_run_at),
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
    elif schedule.enabled and not schedule.next_run_at:
        schedule.next_run_at = _default_next_run_at(schedule.schedule_type, schedule.interval_seconds, None)
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
