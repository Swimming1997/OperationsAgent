from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


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
