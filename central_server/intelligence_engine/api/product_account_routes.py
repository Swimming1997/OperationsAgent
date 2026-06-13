from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


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
