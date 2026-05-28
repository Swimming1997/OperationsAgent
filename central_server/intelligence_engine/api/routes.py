from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence_engine.config import get_settings
from intelligence_engine.domain.enums import ContentWorkflowStatus
from intelligence_engine.services.enrichment_policy import should_enqueue_comment_fetch
from intelligence_engine.services.benchmark_selection import BenchmarkSelectionService
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository
from intelligence_engine.storage.repositories.reference_library_repository import ReferenceLibraryRepository
from intelligence_engine.storage.repositories.workflow_repository import WorkflowRepository
from intelligence_engine.db.models import AccountSession, ContentIdentity, CreatorMonitor, Job, TaskRun, XhsSearchSuggestion, utcnow
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import AccountStatus, JobStatus, JobType, Platform
from intelligence_engine.domain.schemas import (
    AccountCreateRequest,
    AccountCreateResponse,
    AccountSessionCreateRequest,
    AccountSessionRead,
    AgentHeartbeatRequest,
    AgentRegisterRequest,
    AgentRegisterResponse,
    ClaimJobsRequest,
    ClaimJobsResponse,
    ClaimedJob,
    CommentIngestionRequest,
    CommentIngestionResponse,
    CreatorMonitorCreateRequest,
    CreatorMonitorIngestionRequest,
    CreatorMonitorIngestionResponse,
    CreatorMonitorCreateResponse,
    CreatorMonitorJobCreateRequest,
    DetailIngestionRequest,
    DetailIngestionResponse,
    FeedCandidateIngestionRequest,
    FeedCandidateIngestionResponse,
    FeedCandidateIngestionResult,
    FeedCollectCreateRequest,
    IntelligenceContentList,
    JobCompleteRequest,
    JobCreateResponse,
    JobFailRequest,
    JobProgressRequest,
    JobRead,
    JobStartRequest,
)
from intelligence_engine.storage.repositories.account_repository import AccountRepository
from intelligence_engine.domain.xhs_context import merge_xhs_context, prefer_richer_xhs_url
from intelligence_engine.storage.repositories.content_repository import ContentRepository
from intelligence_engine.storage.repositories.creator_repository import CreatorMonitorRepository
from intelligence_engine.storage.repositories.job_repository import JobRepository

router = APIRouter(prefix="/api")


def _job_read(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        payload=job.payload_json,
        checkpoint=job.checkpoint_json,
        result_summary=job.result_summary_json,
        retry_count=job.retry_count,
        last_error_code=job.last_error_code,
        last_error_message=job.last_error_message,
    )


def _enum_value(value):
    return getattr(value, "value", value)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.post("/agents/register", response_model=AgentRegisterResponse)
def register_agent(request: AgentRegisterRequest, db: Session = Depends(get_db)):
    repo = AccountRepository(db)
    agent = repo.register_agent(
        agent_id=request.agent_id,
        employee_id=request.employee_id,
        device_name=request.device_name,
        machine_fingerprint=request.machine_fingerprint,
        agent_version=request.agent_version,
        capabilities=request.capabilities,
    )
    db.commit()
    return AgentRegisterResponse(agent_id=agent.id, status=agent.status)


@router.post("/agents/{agent_id}/heartbeat")
def heartbeat(agent_id: str, request: AgentHeartbeatRequest, db: Session = Depends(get_db)):
    AccountRepository(db).heartbeat(
        agent_id=agent_id,
        status=request.status,
        capabilities=request.capabilities,
        agent_version=request.agent_version,
    )
    db.commit()
    return {"accepted": True, "server_time": datetime.now(timezone.utc).isoformat()}


@router.post("/accounts", response_model=AccountCreateResponse)
def create_account(request: AccountCreateRequest, db: Session = Depends(get_db)):
    account = AccountRepository(db).create_account(
        employee_id=request.employee_id,
        platform=_enum_value(request.platform),
        display_name=request.display_name,
        external_account_id=request.external_account_id,
        business_account_type=request.business_account_type,
        business_account_type_id=request.business_account_type_id,
        metadata=request.metadata,
    )
    db.commit()
    return AccountCreateResponse(account_id=account.id, status=AccountStatus(account.status))


@router.get("/accounts")
def list_accounts(platform: Platform | None = None, status: AccountStatus | None = None, db: Session = Depends(get_db)):
    accounts = AccountRepository(db).list_accounts(
        platform=platform.value if platform else None,
        status=status.value if status else None,
    )
    return [
        {
            "id": account.id,
            "platform": account.platform,
            "display_name": account.display_name,
            "status": account.status,
        }
        for account in accounts
    ]


@router.post("/accounts/{account_id}/sessions")
def create_account_session(account_id: str, request: AccountSessionCreateRequest, db: Session = Depends(get_db)):
    account = AccountRepository(db)
    account_row = db.get(__import__("intelligence_engine.db.models", fromlist=["PlatformAccount"]).PlatformAccount, account_id)
    if not account_row:
        raise HTTPException(status_code=404, detail="account not found")
    session = account.create_session(
        account=account_row,
        local_agent_id=request.local_agent_id,
        session_type=request.session_type,
        profile_ref=request.profile_ref,
        cookie_ref=request.cookie_ref,
        status=request.status,
        session_meta=request.session_meta,
    )
    db.commit()
    return {"session_id": session.id}


@router.get("/accounts/{account_id}/sessions/ready", response_model=AccountSessionRead)
def get_ready_account_session(account_id: str, local_agent_id: str | None = None, db: Session = Depends(get_db)):
    stmt = (
        select(AccountSession)
        .where(AccountSession.account_id == account_id)
        .where(AccountSession.status == "ready")
        .order_by(AccountSession.last_validated_at.desc().nullslast(), AccountSession.created_at.desc())
        .limit(1)
    )
    if local_agent_id:
        stmt = stmt.where(AccountSession.local_agent_id == local_agent_id)
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=404, detail="ready session not found")
    return AccountSessionRead(
        session_id=session.id,
        account_id=session.account_id,
        local_agent_id=session.local_agent_id,
        platform=Platform(session.platform),
        session_type=session.session_type,
        status=session.status,
        session_meta=session.session_meta_json or {},
    )


@router.post("/jobs/feed-collect", response_model=JobCreateResponse)
def create_feed_job(request: FeedCollectCreateRequest, db: Session = Depends(get_db)):
    account = db.get(__import__("intelligence_engine.db.models", fromlist=["PlatformAccount"]).PlatformAccount, request.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    payload = {
        "platform": account.platform,
        "account_id": request.account_id,
        "feed_type": _enum_value(request.feed_type),
        "target_count": request.target_count,
        "refresh_rounds": request.refresh_rounds,
        "per_round_scroll_target": request.per_round_scroll_target,
    }
    job = JobRepository(db).create_job(
        job_type=JobType.FEED_COLLECT,
        account_id=request.account_id,
        local_agent_id=None,
        payload=payload,
        priority=request.priority,
    )
    db.commit()
    return JobCreateResponse(job_id=job.id, status=JobStatus(job.status))


@router.post("/jobs/creator-monitor", response_model=JobCreateResponse)
def create_creator_monitor_job(request: CreatorMonitorJobCreateRequest, db: Session = Depends(get_db)):
    monitor = db.get(__import__("intelligence_engine.db.models", fromlist=["CreatorMonitor"]).CreatorMonitor, request.creator_monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="creator monitor not found")
    job = CreatorMonitorRepository(db).enqueue_monitor_job(monitor=monitor, priority=request.priority)
    db.commit()
    return JobCreateResponse(job_id=job.id, status=JobStatus(job.status))


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = JobRepository(db).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_read(job)


@router.post("/agents/{agent_id}/jobs/claim", response_model=ClaimJobsResponse)
def claim_jobs(agent_id: str, request: ClaimJobsRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    repo = JobRepository(db)
    repo.fail_stale_running_jobs(max_running_seconds=settings.job_running_timeout_seconds)
    jobs = repo.claim_jobs_for_agent(
        agent_id=agent_id,
        supported_job_types=request.supported_job_types,
        max_jobs=request.max_jobs,
        ttl_seconds=get_settings().claim_ttl_seconds,
    )
    db.commit()
    return ClaimJobsResponse(
        jobs=[
            ClaimedJob(
                job_id=job.id,
                job_type=job.job_type,
                account_id=job.account_id,
                payload=job.payload_json,
                checkpoint=job.checkpoint_json,
                claim_expires_at=job.claim_expires_at,
            )
            for job in jobs
        ]
    )


@router.post("/jobs/{job_id}/start", response_model=JobRead)
def start_job(job_id: str, request: JobStartRequest, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    repo.mark_started(job, agent_id=request.agent_id)
    db.commit()
    return _job_read(job)


@router.post("/jobs/{job_id}/progress", response_model=JobRead)
def progress_job(job_id: str, request: JobProgressRequest, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    repo.update_checkpoint(job, checkpoint=request.checkpoint, partial_metrics=request.partial_metrics)
    db.commit()
    return _job_read(job)


@router.post("/jobs/{job_id}/complete", response_model=JobRead)
def complete_job(job_id: str, request: JobCompleteRequest, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    repo.mark_success(job, status=request.status, result_summary=request.result_summary)
    if job.task_run_id:
        from intelligence_engine.services.task_materialization import TaskMaterializationService

        run = db.get(TaskRun, job.task_run_id)
        if run:
            TaskMaterializationService(db).refresh_task_run(run)
    db.commit()
    return _job_read(job)


@router.post("/jobs/{job_id}/fail", response_model=JobRead)
def fail_job(job_id: str, request: JobFailRequest, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    repo.mark_failed(job, error_code=_enum_value(request.error.code), error_message=request.error.message, checkpoint=request.checkpoint)
    db.commit()
    return _job_read(job)


@router.post("/jobs/{job_id}/pause", response_model=JobRead)
def pause_job(job_id: str, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    repo.pause(job)
    db.commit()
    return _job_read(job)


@router.post("/jobs/{job_id}/resume", response_model=JobRead)
def resume_job(job_id: str, db: Session = Depends(get_db)):
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    repo.resume(job)
    db.commit()
    return _job_read(job)


@router.post("/ingestion/feed-candidates", response_model=FeedCandidateIngestionResponse)
def ingest_feed_candidates(request: FeedCandidateIngestionRequest, db: Session = Depends(get_db)):
    repo = ContentRepository(db)
    results = []
    evaluated_content_ids: list[str] = []
    job = db.get(Job, request.job_id)
    rule_set_id = (job.payload_json or {}).get("rule_set_id") if job else None
    for candidate in request.candidates:
        content, is_new, event, detail_job_enqueued, feed_prelim_pass = repo.ingest_feed_candidate(
            job_id=request.job_id,
            account_id=request.account_id,
            candidate=candidate,
        )
        if not is_new and content.latest_snapshot_id:
            repo.evaluate_candidate(content_id=content.id, snapshot_id=content.latest_snapshot_id, rule_set_id=rule_set_id)
        evaluated_content_ids.append(content.id)
        results.append(
            FeedCandidateIngestionResult(
                platform_content_id=candidate.platform_content_id,
                content_id=content.id,
                is_new_content=is_new,
                detail_job_enqueued=detail_job_enqueued,
                discovery_event_id=event.id,
                feed_prelim_pass=feed_prelim_pass,
            )
        )
    db.commit()
    selection = BenchmarkSelectionService(db)
    for content_id in evaluated_content_ids:
        selection.ai_select_by_rules(content_id=content_id, trigger_source="feed_ingestion")
    db.commit()
    return FeedCandidateIngestionResponse(results=results)


@router.post("/ingestion/creator-monitor-items", response_model=CreatorMonitorIngestionResponse)
def ingest_creator_monitor_items(request: CreatorMonitorIngestionRequest, db: Session = Depends(get_db)):
    monitor = db.get(CreatorMonitor, request.creator_monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="creator monitor not found")
    if request.creator_display_name:
        monitor.creator_display_name = request.creator_display_name
    content_repo = ContentRepository(db)
    creator_repo = CreatorMonitorRepository(db)
    job = db.get(Job, request.job_id)
    rule_set_id = (job.payload_json or {}).get("rule_set_id") if job else None
    new_count = 0
    duplicate_count = 0
    detail_jobs = 0
    event_count = 0
    evaluated_content_ids: list[str] = []
    seen_ids: list[str] = []
    for candidate in request.items:
        content, is_new, _event, detail_enqueued, _prelim = content_repo.ingest_feed_candidate(
            job_id=request.job_id,
            account_id=request.account_id,
            candidate=candidate,
            enqueue_detail_job=True,
        )
        seen_ids.append(content.platform_content_id)
        if is_new:
            new_count += 1
            creator_repo.add_event(
                monitor_id=monitor.id,
                content_id=content.id,
                event_type="new_content_detected",
                payload={
                    "platform_content_id": content.platform_content_id,
                    "canonical_url": content.canonical_url,
                    "platform_context": (content.metadata_json or {}).get("platform_context", {}),
                },
            )
            event_count += 1
        else:
            duplicate_count += 1
            if content.latest_snapshot_id:
                content_repo.evaluate_candidate(content_id=content.id, snapshot_id=content.latest_snapshot_id, rule_set_id=rule_set_id)
                evaluated_content_ids.append(content.id)
        if detail_enqueued:
            detail_jobs += 1
    creator_repo.add_event(
        monitor_id=monitor.id,
        event_type="monitor_run_success",
        payload={"items_seen": len(request.items), "new_contents_detected": new_count, "raw_payload": request.raw_payload},
    )
    event_count += 1
    monitor.last_cursor_json = {"last_seen_platform_content_ids": seen_ids}
    db.commit()
    selection = BenchmarkSelectionService(db)
    for content_id in evaluated_content_ids:
        selection.ai_select_by_rules(content_id=content_id, trigger_source="creator_monitor_ingestion")
    db.commit()
    return CreatorMonitorIngestionResponse(
        items_seen=len(request.items),
        new_content_count=new_count,
        duplicate_content_count=duplicate_count,
        detail_job_enqueue_count=detail_jobs,
        creator_event_count=event_count,
    )


@router.post("/ingestion/content-detail", response_model=DetailIngestionResponse)
def ingest_detail(request: DetailIngestionRequest, db: Session = Depends(get_db)):
    content = db.get(ContentIdentity, request.content_id)
    if not content:
        raise HTTPException(status_code=404, detail="content not found")
    job = db.get(Job, request.job_id)
    rule_set_id = (job.payload_json or {}).get("rule_set_id") if job else None
    repo = ContentRepository(db)
    snapshot = repo.create_snapshot(content_id=request.content_id, account_id=job.account_id if job else None, snapshot=request.snapshot)
    repo.evaluate_candidate(
        content_id=request.content_id,
        snapshot_id=snapshot.id,
        rule_set_id=rule_set_id,
    )
    BenchmarkSelectionService(db).ai_select_by_rules(content_id=request.content_id, trigger_source="detail_ingestion")
    content_metadata = dict(content.metadata_json or {})
    content_context = content_metadata.get("platform_context") if isinstance(content_metadata.get("platform_context"), dict) else {}
    job_context = job.payload_json.get("platform_context") if job and isinstance(job.payload_json.get("platform_context"), dict) else {}
    platform_context = (
        merge_xhs_context(content_context, job_context)
        if content.platform == Platform.XHS.value
        else (job_context or content_context)
    )
    if platform_context:
        content_metadata["platform_context"] = platform_context
    if request.snapshot.author_name:
        content_metadata["author_name"] = request.snapshot.author_name
    if request.snapshot.cover_url:
        content_metadata["cover_url"] = request.snapshot.cover_url
    if request.snapshot.title:
        content_metadata["feed_title_or_summary"] = request.snapshot.title
    raw_payload = request.snapshot.raw_payload or {}
    platform_tags = raw_payload.get("platform_tags")
    if isinstance(platform_tags, list) and platform_tags:
        content_metadata["platform_tags"] = platform_tags
    content.metadata_json = content_metadata
    canonical_url = content.canonical_url
    if job and job.payload_json.get("canonical_url"):
        canonical_url = (
            prefer_richer_xhs_url(content.canonical_url, job.payload_json.get("canonical_url"))
            if content.platform == Platform.XHS.value
            else job.payload_json.get("canonical_url")
        )
        content.canonical_url = canonical_url
    comment_job_enqueued = False
    ref_repo = ReferenceLibraryRepository(db)
    state = WorkflowRepository(db).ensure_state(request.content_id)
    workflow_selected = state.workflow_status == ContentWorkflowStatus.SELECTED.value
    if should_enqueue_comment_fetch(
        comment_count=request.snapshot.comment_count,
        in_reference_library=ref_repo.content_in_active_library(request.content_id),
        workflow_selected=workflow_selected,
    ):
        JobRepository(db).create_job(
            job_type=JobType.COMMENT_FETCH,
            account_id=job.account_id if job else None,
            task_run_id=job.task_run_id if job else None,
            payload={
                "content_id": request.content_id,
                "platform": content.platform,
                "platform_content_id": content.platform_content_id,
                "canonical_url": canonical_url,
                "platform_context": platform_context,
                "max_comments": get_settings().default_comment_limit,
                "include_sub_comments": False,
                "rule_set_id": rule_set_id,
            },
            priority=90,
        )
        comment_job_enqueued = True
    db.commit()
    return DetailIngestionResponse(snapshot_id=snapshot.id, candidate_decision_enqueued=True, comment_job_enqueued=comment_job_enqueued)


@router.post("/ingestion/comments", response_model=CommentIngestionResponse)
def ingest_comments(request: CommentIngestionRequest, db: Session = Depends(get_db)):
    inserted, updated, hits = ContentRepository(db).create_or_update_comments(content_id=request.content_id, comments=request.comments)
    content = db.get(ContentIdentity, request.content_id)
    if content and content.latest_snapshot_id:
        job = db.get(Job, request.job_id)
        ContentRepository(db).evaluate_candidate(
            content_id=request.content_id,
            snapshot_id=content.latest_snapshot_id,
            rule_set_id=(job.payload_json or {}).get("rule_set_id") if job else None,
        )
        BenchmarkSelectionService(db).ai_select_by_rules(content_id=request.content_id, trigger_source="comment_ingestion")
    db.commit()
    return CommentIngestionResponse(inserted=inserted, updated=updated, lead_keyword_hits=hits)


@router.post("/creator-monitors", response_model=CreatorMonitorCreateResponse)
def create_creator_monitor(request: CreatorMonitorCreateRequest, db: Session = Depends(get_db)):
    monitor = CreatorMonitorRepository(db).create_monitor(
        platform=_enum_value(request.platform),
        creator_platform_id=request.creator_platform_id,
        creator_display_name=request.creator_display_name,
        monitor_group_key=request.monitor_group_key,
        mapped_business_account_type=request.mapped_business_account_type,
        check_interval_seconds=request.check_interval_seconds,
    )
    db.commit()
    return CreatorMonitorCreateResponse(creator_monitor_id=monitor.id)


@router.get("/creator-monitors")
def list_creator_monitors(db: Session = Depends(get_db)):
    return [
        {
            "id": monitor.id,
            "platform": monitor.platform,
            "creator_platform_id": monitor.creator_platform_id,
            "creator_display_name": monitor.creator_display_name,
            "enabled": monitor.enabled,
        }
        for monitor in CreatorMonitorRepository(db).list_monitors()
    ]


@router.post("/ingestion/xhs-search-suggestions")
def ingest_xhs_search_suggestions(request: dict, db: Session = Depends(get_db)):
    items = request.get("items") or []
    inserted = 0
    for item in items:
        fetched_at_raw = item.get("fetched_at")
        fetched_at = datetime.fromisoformat(str(fetched_at_raw).replace("Z", "+00:00")) if fetched_at_raw else utcnow()
        row = XhsSearchSuggestion(
            platform="xhs",
            core_keyword=str(item.get("core_keyword") or request.get("core_keyword") or ""),
            suggested_keyword=str(item.get("suggested_keyword") or ""),
            suggestion_rank=item.get("suggestion_rank"),
            source_account_id=request.get("account_id"),
            fetched_at=fetched_at,
            raw_payload_json=item.get("raw_payload") or {},
        )
        db.add(row)
        inserted += 1
    db.commit()
    return {"inserted": inserted}


@router.get("/intelligence/contents", response_model=IntelligenceContentList)
def list_intelligence_contents(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    items, total = ContentRepository(db).list_intelligence_contents(page=page, page_size=page_size)
    return IntelligenceContentList(items=items, page=page, page_size=page_size, total=total)
