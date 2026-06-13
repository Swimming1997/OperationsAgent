from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.api.account_access import ensure_account_readable, get_principal_employee_id
from intelligence_engine.db.models import (
    BenchmarkGroup,
    BusinessAccountType,
    BusinessAccountTypeBenchmarkGroup,
    BusinessAccountTypeRuleSet,
    KeywordRuleSet,
    PlatformAccount,
    TaskSchedule,
    TaskTemplate,
)
from intelligence_engine.services.task_template_config import parse_template_config_dict, strip_legacy_template_config_keys
from intelligence_engine.domain.enums import AccountRole, UserRoleName
from intelligence_engine.security.auth import Principal


def _is_operator_only(principal: Principal) -> bool:
    return principal.has_role(UserRoleName.OPERATOR) and not principal.has_role(
        UserRoleName.ADMIN, UserRoleName.SUPERVISOR
    )


def operator_business_type_ids(db: Session, principal: Principal) -> set[str]:
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


def list_visible_business_type_ids(db: Session, principal: Principal) -> set[str] | None:
    """None means no filter (admin/supervisor sees all business types)."""
    if not _is_operator_only(principal):
        return None
    return operator_business_type_ids(db, principal)


def ensure_business_type_in_scope(db: Session, principal: Principal, business_account_type_id: str) -> None:
    if not db.get(BusinessAccountType, business_account_type_id):
        raise HTTPException(status_code=404, detail="business account type not found")
    visible = list_visible_business_type_ids(db, principal)
    if visible is not None and business_account_type_id not in visible:
        raise HTTPException(status_code=403, detail="insufficient permission for this business account type")


def legacy_executor_account_id(template: TaskTemplate) -> str | None:
    config = parse_template_config_dict(template.config_json)
    value = config.get("executor_account_id")
    return value if isinstance(value, str) and value else None


def maybe_repair_legacy_task_template(db: Session, template: TaskTemplate) -> bool:
    """Backfill business_account_type_id and strip executor_account_id from stored config."""
    changed = False
    config = parse_template_config_dict(template.config_json)
    executor_account_id = legacy_executor_account_id(template) if isinstance(config, dict) else None

    if not template.business_account_type_id:
        account_id = template.account_id or executor_account_id
        if account_id:
            account = db.get(PlatformAccount, account_id)
            if account and account.business_account_type_id:
                template.business_account_type_id = account.business_account_type_id
                changed = True

    if isinstance(config, dict):
        stripped = strip_legacy_template_config_keys(config)
        if stripped != config:
            template.config_json = stripped
            changed = True

    if changed:
        db.flush()
    return changed


def ensure_template_readable(db: Session, principal: Principal, template: TaskTemplate) -> None:
    maybe_repair_legacy_task_template(db, template)
    if not template.business_account_type_id:
        if _is_operator_only(principal):
            raise HTTPException(status_code=403, detail="template has no business account type")
        return
    visible = list_visible_business_type_ids(db, principal)
    if visible is not None and template.business_account_type_id not in visible:
        raise HTTPException(status_code=403, detail="insufficient permission for this task template")


def ensure_template_writable(principal: Principal, template: TaskTemplate) -> None:
    if not _is_operator_only(principal):
        return
    if template.created_by_user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="仅创建人可编辑该任务模板")


def ensure_template_schedule_creatable(principal: Principal, template: TaskTemplate) -> None:
    """Operator may only create schedules on templates they own."""
    if not _is_operator_only(principal):
        return
    if template.created_by_user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="仅可在自己创建的任务模板上配置定时调度")


def ensure_schedule_writable(principal: Principal, schedule: TaskSchedule) -> None:
    if not _is_operator_only(principal):
        return
    if schedule.created_by_user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="仅可编辑自己创建的定时调度")


def rule_set_binding_status(
    db: Session,
    *,
    business_account_type_id: str | None,
    rule_set_id: str | None,
) -> tuple[bool, str]:
    if not rule_set_id:
        return True, "未选择规则集"
    rule_set = db.get(KeywordRuleSet, rule_set_id)
    if not rule_set:
        return False, f"规则集不存在: {rule_set_id}"
    if not business_account_type_id:
        return False, "缺少业务类型，无法校验规则集绑定"
    binding = db.scalar(
        select(BusinessAccountTypeRuleSet.id).where(
            BusinessAccountTypeRuleSet.business_account_type_id == business_account_type_id,
            BusinessAccountTypeRuleSet.rule_set_id == rule_set_id,
        )
    )
    business_type = db.get(BusinessAccountType, business_account_type_id)
    business_type_name = business_type.name if business_type else business_account_type_id
    if not binding:
        return False, f"规则集 {rule_set.name} 未绑定到业务类型 {business_type_name}"
    return True, f"规则集 {rule_set.name} 已绑定到业务类型 {business_type_name}"


def benchmark_group_binding_status(
    db: Session,
    *,
    business_account_type_id: str | None,
    benchmark_group_id: str | None,
) -> tuple[bool, str]:
    if not benchmark_group_id:
        return False, "缺少对标账号组"
    group = db.get(BenchmarkGroup, benchmark_group_id)
    if not group:
        return False, f"对标账号组不存在: {benchmark_group_id}"
    if not business_account_type_id:
        return False, "缺少业务类型，无法校验对标账号组绑定"
    binding = db.scalar(
        select(BusinessAccountTypeBenchmarkGroup.id).where(
            BusinessAccountTypeBenchmarkGroup.business_account_type_id == business_account_type_id,
            BusinessAccountTypeBenchmarkGroup.benchmark_group_id == benchmark_group_id,
        )
    )
    business_type = db.get(BusinessAccountType, business_account_type_id)
    business_type_name = business_type.name if business_type else business_account_type_id
    if not binding:
        return False, f"对标账号组 {group.name} 未绑定到业务类型 {business_type_name}"
    return True, f"对标账号组 {group.name} 已绑定到业务类型 {business_type_name}"


def validate_template_bindings(
    db: Session,
    *,
    business_account_type_id: str,
    rule_set_id: str | None,
    benchmark_group_id: str | None = None,
    require_benchmark: bool = False,
) -> None:
    ok, message = rule_set_binding_status(db, business_account_type_id=business_account_type_id, rule_set_id=rule_set_id)
    if rule_set_id and not ok:
        raise HTTPException(status_code=400, detail=message)
    if require_benchmark or benchmark_group_id:
        ok, message = benchmark_group_binding_status(
            db,
            business_account_type_id=business_account_type_id,
            benchmark_group_id=benchmark_group_id,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=message)


def ensure_executor_account_for_template(
    db: Session,
    principal: Principal,
    template: TaskTemplate,
    executor_account_id: str,
) -> PlatformAccount:
    account = db.get(PlatformAccount, executor_account_id)
    if not account:
        raise HTTPException(status_code=404, detail="executor account not found")
    if template.business_account_type_id and account.business_account_type_id != template.business_account_type_id:
        raise HTTPException(status_code=400, detail="executor account business type does not match template")
    if not template.business_account_type_id and account.business_account_type_id:
        template.business_account_type_id = account.business_account_type_id
        db.flush()
    role = getattr(account, "account_role", None) or AccountRole.INTELLIGENCE_COLLECTOR.value
    if role != AccountRole.INTELLIGENCE_COLLECTOR.value:
        raise HTTPException(status_code=400, detail=f"account cannot run intelligence collection tasks (role={role})")
    if _is_operator_only(principal):
        ensure_account_readable(db, principal, account)
    return account


def template_permissions(principal: Principal, template: TaskTemplate) -> dict[str, bool]:
    can_edit = not _is_operator_only(principal) or template.created_by_user_id == principal.user_id
    return {"can_edit": can_edit, "can_run": True, "can_schedule": can_edit, "can_delete": can_edit}


def ensure_template_deletable(principal: Principal, template: TaskTemplate) -> None:
    ensure_template_writable(principal, template)
