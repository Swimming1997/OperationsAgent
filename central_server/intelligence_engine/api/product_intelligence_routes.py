from intelligence_engine.api.product_common import *
from intelligence_engine.domain.schemas import LocalContentPromoteRequest, LocalContentPromoteResponse


router = APIRouter(prefix="/api")


@router.post("/intelligence/contents/promote", response_model=LocalContentPromoteResponse)
def promote_local_content(
    request: LocalContentPromoteRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(
        require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)
    ),
) -> LocalContentPromoteResponse:
    """Local-first: persist a selected content into central before building a material entry.

    Central only stores filtered material, so collected content lives locally until
    an operator promotes it. This upserts the content identity + a detail snapshot
    (no job / discovery event needed) and returns the central content id.
    """
    repo = ContentRepository(db)
    content, is_new = repo.upsert_identity_from_candidate(request.candidate)
    WorkflowRepository(db).ensure_state(content.id)
    if request.detail is not None:
        repo.create_snapshot(content_id=content.id, account_id=None, snapshot=request.detail)
    db.commit()
    return LocalContentPromoteResponse(content_id=content.id, is_new=is_new)


@router.get("/intelligence/contents/product", response_model=IntelligenceContentProductList)
def list_product_intelligence_contents(
    platform: Platform | None = None,
    source_surface: SourceSurface | None = None,
    candidate_bucket: str | None = Query(default=None),
    workflow_status: str | None = Query(default=None),
    assigned_to_user_id: str | None = None,
    business_keyword: str | None = None,
    content_query: str | None = None,
    search_keyword: str | None = None,
    discovered_after: datetime | None = None,
    discovered_before: datetime | None = None,
    data_status: ContentDataStatus | None = None,
    tag: str | None = None,
    platform_tag: str | None = None,
    manual_tag: str | None = None,
    manual_tag_id: str | None = None,
    untagged: bool | None = None,
    search_sort: str | None = None,
    note_type_filter: str | None = None,
    publish_time_filter: str | None = None,
    min_like_count: int | None = None,
    min_comment_count: int | None = None,
    min_collect_count: int | None = None,
    in_reference_library: bool | None = None,
    reference_library_type: str | None = None,
    selection_source: str | None = None,
    reference_rating: str | None = None,
    sort_by: str = "latest_discovered_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES)),
):
    candidate_bucket_values = _split_enum_filter(candidate_bucket, CandidateBucket)
    workflow_status_values = _split_enum_filter(workflow_status, ContentWorkflowStatus)
    operator_scope = resolve_operator_intelligence_list_scope(db, principal, assigned_to_user_id)
    list_assigned_to_user_id = operator_scope.assigned_to_user_id if operator_scope else assigned_to_user_id
    list_discovered_by_account_ids = (
        list(operator_scope.discovered_by_account_ids) if operator_scope else None
    )
    items, total = WorkflowRepository(db).list_intelligence_contents(
        page=page,
        page_size=page_size,
        platform=_enum_value(platform) if platform else None,
        source_surface=_enum_value(source_surface) if source_surface else None,
        candidate_buckets=candidate_bucket_values,
        workflow_statuses=workflow_status_values,
        assigned_to_user_id=list_assigned_to_user_id,
        discovered_by_account_ids=list_discovered_by_account_ids,
        business_keyword=business_keyword,
        content_query=content_query,
        search_keyword=search_keyword,
        discovered_after=discovered_after,
        discovered_before=discovered_before,
        data_status=_enum_value(data_status) if data_status else None,
        tag=tag,
        platform_tag=platform_tag,
        manual_tag=manual_tag,
        manual_tag_id=manual_tag_id,
        untagged=untagged,
        search_sort=search_sort,
        note_type_filter=note_type_filter,
        publish_time_filter=publish_time_filter,
        min_like_count=min_like_count,
        min_comment_count=min_comment_count,
        min_collect_count=min_collect_count,
        in_reference_library=in_reference_library,
        reference_library_type=reference_library_type,
        selection_source=selection_source,
        reference_rating=reference_rating,
        sort_by=sort_by,
        sort_order=sort_order,
        pool_only=True,
    )
    db.commit()
    return IntelligenceContentProductList(items=items, page=page, page_size=page_size, total=total)


@router.get("/intelligence/contents/{content_id}/product-detail", response_model=IntelligenceContentProductDetail)
def get_intelligence_content_product_detail(content_id: str, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(*INTELLIGENCE_READ_ROLES))):
    content = _ensure_content(content_id, db)
    repo = WorkflowRepository(db)
    state = repo.ensure_state(content_id)
    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id) if content.latest_snapshot_id else None
    comments = list(
        db.scalars(
            select(CommentSnapshot)
            .where(CommentSnapshot.content_id == content_id)
            .order_by(CommentSnapshot.created_time.desc().nullslast(), CommentSnapshot.fetched_at.desc())
            .limit(20)
        )
    )
    decision = repo.latest_decision_for_content(content_id)
    notes = repo.list_notes(content_id=content_id)
    assignments = repo.assignment_history(content_id)
    discoveries = repo.discovery_events(content_id)
    discovery_meta_rows = [item.discovery_meta_json for item in discoveries if item.discovery_meta_json]
    metadata = content.metadata_json or {}
    summary = repo._discovery_summary(content_id)
    comment_count = summary.get("comment_snapshot_count") or 0
    enrichment_flags = metadata.get("enrichment_flags") if isinstance(metadata.get("enrichment_flags"), dict) else {}
    data_status_value = derive_data_status(
        latest_snapshot_id=content.latest_snapshot_id,
        comment_snapshot_count=comment_count,
        detail_fetch_failed=bool(enrichment_flags.get("detail_failed")),
        comment_fetch_failed=bool(enrichment_flags.get("comment_failed")),
    )
    ref_items = ReferenceLibraryRepository(db).list_for_content(content_id)
    active_jobs = list(
        db.scalars(
            select(Job).where(
                Job.job_type.in_([JobType.DETAIL_FETCH.value, JobType.COMMENT_FETCH.value]),
                Job.status.in_([JobStatus.PENDING.value, JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            )
        )
    )
    pending_detail_job = next((job.id for job in active_jobs if job.job_type == JobType.DETAIL_FETCH.value and (job.payload_json or {}).get("content_id") == content_id), None)
    pending_comment_job = next((job.id for job in active_jobs if job.job_type == JobType.COMMENT_FETCH.value and (job.payload_json or {}).get("content_id") == content_id), None)
    media = MediaService()
    db.commit()
    return IntelligenceContentProductDetail(
        identity=ContentIdentityDetail(
            id=content.id,
            platform=content.platform,
            platform_content_id=content.platform_content_id,
            canonical_url=content.canonical_url,
            content_type=content.content_type,
            first_seen_at=content.first_seen_at,
            last_seen_at=content.last_seen_at,
            metadata=content.metadata_json or {},
        ),
        latest_snapshot=(
            ContentSnapshotDetail(
                id=snapshot.id,
                title=snapshot.title,
                body_text=snapshot.body_text,
                author_platform_id=snapshot.author_platform_id,
                author_name=snapshot.author_name,
                author_avatar_url=snapshot.author_avatar_url,
                cover_url=snapshot.cover_url,
                cover_display_url=media.build_cover_display_url_for_snapshot(content_id, snapshot, content.metadata_json or {}),
                image_urls=snapshot.image_urls_json or [],
                image_display_urls=media.build_image_display_urls_for_snapshot(content_id, snapshot, content.metadata_json or {}),
                video_url=snapshot.video_url,
                like_count=snapshot.like_count,
                comment_count=snapshot.comment_count,
                collect_count=snapshot.collect_count,
                share_count=snapshot.share_count,
                publish_time=snapshot.publish_time,
                fetched_at=snapshot.fetched_at,
            )
            if snapshot
            else None
        ),
        comments=[
            CommentSnapshotDetail(
                id=comment.id,
                platform_comment_id=comment.platform_comment_id,
                parent_platform_comment_id=comment.parent_platform_comment_id,
                author_platform_id=comment.author_platform_id,
                author_name=comment.author_name,
                body_text=comment.body_text,
                like_count=comment.like_count,
                created_time=comment.created_time,
                fetched_at=comment.fetched_at,
            )
            for comment in comments
        ],
        latest_candidate_decision=(
            CandidateDecisionDetail(
                id=decision.id,
                candidate_bucket=decision.candidate_bucket,
                business_keyword_hits=decision.business_keyword_hits_json or [],
                lead_keyword_hits=decision.lead_keyword_hits_json or [],
                comment_keyword_hits=decision.comment_keyword_hits_json or [],
                decision_reason=decision.decision_reason_json or {},
                evaluated_at=decision.evaluated_at,
            )
            if decision
            else None
        ),
        workflow_state=_workflow_read(state),
        notes=[ContentOperatorNoteRead(id=note.id, content_id=note.content_id, user_id=note.user_id, note=note.note, created_at=note.created_at) for note in notes],
        assignment_history=[
            AssignmentHistoryItem(id=item.id, assigned_to_user_id=item.assigned_to_user_id, assigned_by_user_id=item.assigned_by_user_id, assigned_at=item.assigned_at, status=item.status, remark=item.remark)
            for item in assignments
        ],
        discovery_events_summary=[
            DiscoveryEventSummaryItem(
                id=item.id,
                source_surface=item.source_surface,
                feed_type=item.feed_type,
                feed_position=item.feed_position,
                discovered_at=item.discovered_at,
                account_id=item.account_id,
                job_id=item.job_id,
                search_keyword=(item.discovery_meta_json or {}).get("search_keyword"),
                search_keywords=(item.discovery_meta_json or {}).get("search_keywords") or [],
            )
            for item in discoveries
        ],
        reference_library_items=[
            ReferenceLibraryItemRead(**ReferenceLibraryRepository(db)._item_dict(item, content, snapshot))
            for item in ref_items
        ],
        platform_tags=extract_platform_tags(metadata, snapshot.raw_payload_json if snapshot else None),
        search_tags=extract_search_tags(metadata, discovery_meta_rows),
        manual_tags=ManualTagRepository(db).list_content_tag_names(content_id) or extract_manual_tags(metadata),
        data_status=data_status_value,
        pending_detail_job_id=pending_detail_job,
        pending_comment_job_id=pending_comment_job,
    )


@router.post("/intelligence/contents/{content_id}/assign", response_model=ContentWorkflowRead)
def assign_intelligence_content(content_id: str, request: ContentAssignRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR))):
    if not db.get(ContentIdentity, content_id):
        raise HTTPException(status_code=404, detail="content not found")
    state = WorkflowRepository(db).assign(
        content_id=content_id,
        assigned_to_user_id=request.assigned_to_user_id,
        assigned_by_user_id=request.assigned_by_user_id,
        remark=request.remark,
    )
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/{content_id}/select", response_model=ContentWorkflowRead)
def select_intelligence_content(content_id: str, request: ContentStatusActionRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    state = WorkflowRepository(db).set_status(content_id=content_id, status=ContentWorkflowStatus.SELECTED, user_id=request.user_id, note=request.note)
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/{content_id}/discard", response_model=ContentWorkflowRead)
def discard_intelligence_content(content_id: str, request: ContentStatusActionRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    state = WorkflowRepository(db).set_status(content_id=content_id, status=ContentWorkflowStatus.DISCARDED, user_id=request.user_id, note=request.note)
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/{content_id}/archive", response_model=ContentWorkflowRead)
def archive_intelligence_content(content_id: str, request: ContentStatusActionRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    state = WorkflowRepository(db).set_status(content_id=content_id, status=ContentWorkflowStatus.ARCHIVED, user_id=request.user_id, note=request.note)
    db.commit()
    return _workflow_read(state)


@router.post("/intelligence/contents/bulk-status", response_model=ContentBulkStatusResponse)
def bulk_set_intelligence_content_status(
    request: ContentBulkStatusRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR)),
):
    if len(request.content_ids) > 100:
        raise HTTPException(status_code=400, detail="bulk content limit exceeded")
    status_by_action = {
        "select": ContentWorkflowStatus.SELECTED,
        "discard": ContentWorkflowStatus.DISCARDED,
        "archive": ContentWorkflowStatus.ARCHIVED,
    }
    status = status_by_action.get(request.action)
    if not status:
        raise HTTPException(status_code=400, detail="unsupported bulk status action")

    repo = WorkflowRepository(db)
    succeeded: list[ContentWorkflowRead] = []
    failed: list[ContentBulkStatusFailure] = []
    actor_id = request.user_id or principal.user_id

    for content_id in request.content_ids:
        if not db.get(ContentIdentity, content_id):
            failed.append(ContentBulkStatusFailure(content_id=content_id, code="not_found", message="content not found"))
            continue
        try:
            state = repo.set_status(content_id=content_id, status=status, user_id=actor_id, note=request.note)
            succeeded.append(_workflow_read(state))
        except Exception as exc:
            failed.append(ContentBulkStatusFailure(content_id=content_id, code="update_failed", message=str(exc)))

    db.commit()
    return ContentBulkStatusResponse(succeeded=succeeded, failed=failed)


@router.post("/intelligence/contents/{content_id}/notes", response_model=ContentOperatorNoteRead)
def add_intelligence_content_note(content_id: str, request: ContentNoteCreateRequest, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    if not db.get(ContentIdentity, content_id):
        raise HTTPException(status_code=404, detail="content not found")
    note = WorkflowRepository(db).add_note(content_id=content_id, user_id=request.user_id, note=request.note)
    db.commit()
    return ContentOperatorNoteRead(id=note.id, content_id=note.content_id, user_id=note.user_id, note=note.note, created_at=note.created_at)


@router.get("/intelligence/contents/{content_id}/notes", response_model=list[ContentOperatorNoteRead])
def list_intelligence_content_notes(content_id: str, db: Session = Depends(get_db), _principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    return [
        ContentOperatorNoteRead(id=note.id, content_id=note.content_id, user_id=note.user_id, note=note.note, created_at=note.created_at)
        for note in WorkflowRepository(db).list_notes(content_id=content_id)
    ]


@router.patch("/intelligence/contents/{content_id}/manual-tags", response_model=ContentIdentityDetail)
def update_intelligence_manual_tags(content_id: str, request: ManualTagsUpdateRequest, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    service = ManualTagService(db)
    tag_ids = list(request.tag_ids)
    if not tag_ids and request.manual_tags:
        from intelligence_engine.storage.repositories.manual_tag_repository import ManualTagRepository

        repo = ManualTagRepository(db)
        service.ensure_bootstrap()
        for raw_name in request.manual_tags:
            name = repo.normalize_name(raw_name)
            if not name:
                continue
            tag = repo.get_by_name(name)
            if not tag:
                tag = repo.create_tag(name=name, created_by_user_id=request.user_id or principal.user_id)
            tag_ids.append(tag.id)
    try:
        content = service.set_content_tags(
            content_id=content_id,
            tag_ids=tag_ids,
            principal=principal,
            user_id=request.user_id or principal.user_id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="content not found")
    except ManualTagActionError as error:
        raise HTTPException(status_code=400, detail={"code": error.code, "message": error.message})
    db.commit()
    return ContentIdentityDetail(
        id=content.id,
        platform=content.platform,
        platform_content_id=content.platform_content_id,
        canonical_url=content.canonical_url,
        content_type=content.content_type,
        first_seen_at=content.first_seen_at,
        last_seen_at=content.last_seen_at,
        metadata=content.metadata_json or {},
    )


@router.post("/intelligence/contents/{content_id}/enqueue-detail-fetch", response_model=EnqueueFetchResponse)
def enqueue_intelligence_detail_fetch(content_id: str, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    repo = ContentRepository(db)
    try:
        account_id = _manual_fetch_account_id(db, repo, content_id=content_id, principal=principal)
        run = _create_manual_fetch_task_run(db, account_id=account_id, requested_by_user_id=principal.user_id)
        job = repo.enqueue_detail_fetch(content_id=content_id, account_id=account_id, task_run_id=run.id)
        TaskMaterializationService(db).refresh_task_run(run)
    except ValueError:
        raise HTTPException(status_code=404, detail="content not found")
    db.commit()
    return EnqueueFetchResponse(job_id=job.id, job_type=job.job_type, status=job.status)


@router.post("/intelligence/contents/{content_id}/enqueue-comment-fetch", response_model=EnqueueFetchResponse)
def enqueue_intelligence_comment_fetch(content_id: str, db: Session = Depends(get_db), principal: Principal = Depends(require_any_role(UserRoleName.ADMIN, UserRoleName.SUPERVISOR, UserRoleName.OPERATOR))):
    repo = ContentRepository(db)
    try:
        account_id = _manual_fetch_account_id(db, repo, content_id=content_id, principal=principal)
        run = _create_manual_fetch_task_run(db, account_id=account_id, requested_by_user_id=principal.user_id)
        job = repo.enqueue_comment_fetch(content_id=content_id, account_id=account_id, task_run_id=run.id)
        TaskMaterializationService(db).refresh_task_run(run)
    except ValueError:
        raise HTTPException(status_code=404, detail="content not found")
    db.commit()
    return EnqueueFetchResponse(job_id=job.id, job_type=job.job_type, status=job.status)
