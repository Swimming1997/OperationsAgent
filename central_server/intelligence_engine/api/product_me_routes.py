from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


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
