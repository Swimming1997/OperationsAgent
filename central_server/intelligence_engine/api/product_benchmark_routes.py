from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


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
