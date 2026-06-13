from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


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
    limit: int = 100,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    stmt = select(XhsSearchSuggestion).order_by(XhsSearchSuggestion.fetched_at.desc()).limit(limit)
    if core_keyword:
        stmt = stmt.where(XhsSearchSuggestion.core_keyword == core_keyword)
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
