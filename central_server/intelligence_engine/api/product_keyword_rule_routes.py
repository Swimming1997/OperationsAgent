from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


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
