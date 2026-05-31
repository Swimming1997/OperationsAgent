from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from intelligence_engine.db.session import get_db
from intelligence_engine.domain.product_schemas import (
    ManualTagCreateRequest,
    ManualTagListResponse,
    ManualTagRead,
)
from intelligence_engine.security.auth import Principal, require_any_role
from intelligence_engine.security.intelligence_access import INTELLIGENCE_READ_ROLES, INTELLIGENCE_WRITE_ROLES, INTELLIGENCE_WRITE_ROLES
from intelligence_engine.services.manual_tag_service import ManualTagActionError, ManualTagService
from intelligence_engine.domain.enums import UserRoleName

router = APIRouter(prefix="/api/manual-tags", tags=["manual-tags"])


def _raise_action_error(error: ManualTagActionError) -> None:
    status = 403 if error.code == "forbidden" else 404 if error.code == "not_found" else 400
    raise HTTPException(status_code=status, detail={"code": error.code, "message": error.message})


def _to_read(summary: dict, *, principal: Principal, service: ManualTagService) -> ManualTagRead:
    return ManualTagRead(
        id=summary["id"],
        name=summary["name"],
        status=summary["status"],
        is_system=summary["is_system"],
        created_by_user_id=summary["created_by_user_id"],
        usage_count=summary["usage_count"],
        created_at=summary["created_at"],
        updated_at=summary["updated_at"],
        archived_at=summary.get("archived_at"),
        can_delete=service.can_operator_delete(summary=summary, principal=principal),
    )


@router.get("", response_model=ManualTagListResponse)
def list_manual_tags(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    service = ManualTagService(db)
    if include_archived and principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        items = service.list_manageable_tags()
    else:
        items = service.list_active_tags()
    return ManualTagListResponse(items=[_to_read(item, principal=principal, service=service) for item in items])


@router.post("", response_model=ManualTagRead)
def create_manual_tag(
    request: ManualTagCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_WRITE_ROLES)),
):
    service = ManualTagService(db)
    try:
        summary = service.create_tag(name=request.name, principal=principal)
    except ManualTagActionError as error:
        _raise_action_error(error)
    db.commit()
    return _to_read(summary, principal=principal, service=service)


@router.delete("/{tag_id}")
def delete_manual_tag_for_operator(
    tag_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_WRITE_ROLES)),
):
    if principal.has_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR):
        raise HTTPException(status_code=400, detail="use archive or hard delete endpoints")
    service = ManualTagService(db)
    try:
        service.delete_tag_for_operator(tag_id=tag_id, principal=principal)
    except ManualTagActionError as error:
        _raise_action_error(error)
    db.commit()
    return {"ok": True}


@router.post("/{tag_id}/archive", response_model=ManualTagRead)
def archive_manual_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    service = ManualTagService(db)
    try:
        summary = service.archive_tag(tag_id=tag_id, principal=principal)
    except ManualTagActionError as error:
        _raise_action_error(error)
    db.commit()
    return _to_read(summary, principal=principal, service=service)


@router.post("/{tag_id}/restore", response_model=ManualTagRead)
def restore_manual_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    service = ManualTagService(db)
    try:
        summary = service.restore_tag(tag_id=tag_id, principal=principal)
    except ManualTagActionError as error:
        _raise_action_error(error)
    db.commit()
    return _to_read(summary, principal=principal, service=service)


@router.delete("/{tag_id}/hard")
def hard_delete_manual_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR)),
):
    service = ManualTagService(db)
    try:
        service.hard_delete_tag(tag_id=tag_id, principal=principal)
    except ManualTagActionError as error:
        _raise_action_error(error)
    db.commit()
    return {"ok": True}
