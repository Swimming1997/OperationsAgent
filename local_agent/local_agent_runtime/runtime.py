from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import httpx

from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe
from local_agent_runtime.connectors.xhs.creator import XhsCreatorConnector, XhsCreatorFetchError
from local_agent_runtime.connectors.xhs.cover_capture import attach_cover_bytes
from local_agent_runtime.connectors.xhs.detail_probe import XhsDetailProbe
from local_agent_runtime.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from local_agent_runtime.connectors.xhs.search_suggest_probe import XhsSearchSuggestProbe
from local_agent_runtime.audit.summary import engine_audit_summary
from local_agent_runtime.enums import ErrorCode, JobStatus, JobType, Platform, SessionStatus
from local_agent_runtime.contracts import (
    CommentIngestionRequest,
    CreatorMonitorIngestionRequest,
    DetailIngestionRequest,
    FeedCandidateIngestionRequest,
)
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider


@dataclass(frozen=True)
class AgentRuntimeConfig:
    center_base_url: str = "http://127.0.0.1:8000"
    agent_id: str | None = None
    employee_id: str | None = None
    device_name: str = field(default_factory=socket.gethostname)
    machine_fingerprint: str = field(default_factory=socket.gethostname)
    agent_version: str = "0.1.0"
    project_root: str | None = None
    cdp_url: str | None = "http://127.0.0.1:9222"
    account_sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    poll_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 30.0
    max_jobs_per_claim: int = 1
    local_bridge_enabled: bool = True
    local_bridge_host: str = "127.0.0.1"
    local_bridge_port: int = 18765
    local_bridge_token: str | None = None
    supports_account_login: bool = True
    supported_job_types: tuple[str, ...] = (
        JobType.FEED_COLLECT.value,
        JobType.DETAIL_FETCH.value,
        JobType.COMMENT_FETCH.value,
        JobType.CREATOR_MONITOR.value,
        JobType.SEARCH_COLLECT.value,
        JobType.XHS_SEARCH_SUGGEST.value,
    )


@dataclass(frozen=True)
class ClaimedJobPayload:
    job_id: str
    job_type: str
    account_id: str | None
    payload: dict[str, Any]
    checkpoint: dict[str, Any]


@dataclass(frozen=True)
class JobExecutionResult:
    status: str
    result_summary: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)


class RuntimeFailure(Exception):
    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False, raw_context: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.raw_context = raw_context or {}


def build_agent_capabilities_payload(config: AgentRuntimeConfig) -> dict[str, Any]:
    return {
        "platforms": [Platform.XHS.value],
        "supports_cdp": bool(config.cdp_url),
        "supports_account_login": config.supports_account_login,
        "job_types": list(config.supported_job_types),
        "runtime": "local_agent_runtime_v1",
    }


@dataclass(frozen=True)
class ClaimedLoginSessionPayload:
    session_id: str
    platform_account_id: str
    profile_key: str
    cdp_port: int
    fresh_profile: bool = False


class CenterClientProtocol(Protocol):
    async def register_agent(self, config: AgentRuntimeConfig) -> str: ...
    async def heartbeat(
        self,
        agent_id: str,
        running_job_ids: list[str],
        *,
        status: str = "online",
        capabilities: dict[str, Any] | None = None,
        agent_version: str | None = None,
    ) -> None: ...
    async def claim_login_sessions(self, agent_id: str, *, max_sessions: int = 1) -> list[ClaimedLoginSessionPayload]: ...
    async def claim_jobs(self, agent_id: str, supported_job_types: tuple[str, ...], max_jobs: int) -> list[ClaimedJobPayload]: ...
    async def start_job(self, job_id: str, agent_id: str) -> None: ...
    async def progress_job(self, job_id: str, agent_id: str, checkpoint: dict[str, Any], partial_metrics: dict[str, Any] | None = None) -> None: ...
    async def complete_job(self, job_id: str, agent_id: str, status: str, result_summary: dict[str, Any]) -> None: ...
    async def fail_job(self, job_id: str, agent_id: str, failure: RuntimeFailure, checkpoint: dict[str, Any]) -> None: ...


class CenterClient:
    def __init__(self, *, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        # Avoid routing 127.0.0.1 through HTTP_PROXY / system proxy (common source of 502 on register).
        self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def check_health(self) -> None:
        response = await self._client.get(f"{self.base_url}/api/health")
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            raise RuntimeError(f"central health unexpected payload: {payload!r}")

    async def register_agent(self, config: AgentRuntimeConfig) -> str:
        payload: dict[str, Any] = {
            "device_name": config.device_name,
            "machine_fingerprint": config.machine_fingerprint,
            "agent_version": config.agent_version,
            "capabilities": build_agent_capabilities_payload(config),
        }
        if config.employee_id:
            payload["employee_id"] = config.employee_id
        if config.agent_id:
            payload["agent_id"] = config.agent_id
        response = await self._client.post(
            f"{self.base_url}/api/agents/register",
            json=payload,
        )
        response.raise_for_status()
        return response.json()["agent_id"]

    async def heartbeat(
        self,
        agent_id: str,
        running_job_ids: list[str],
        *,
        status: str = "online",
        capabilities: dict[str, Any] | None = None,
        agent_version: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "status": status,
            "running_job_ids": running_job_ids,
        }
        if agent_version:
            payload["agent_version"] = agent_version
        if capabilities:
            payload["capabilities"] = capabilities
        response = await self._client.post(
            f"{self.base_url}/api/agents/{agent_id}/heartbeat",
            json=payload,
        )
        response.raise_for_status()

    async def claim_login_sessions(self, agent_id: str, *, max_sessions: int = 1) -> list[ClaimedLoginSessionPayload]:
        response = await self._client.post(
            f"{self.base_url}/api/agents/{agent_id}/login-sessions/claim",
            params={"max_sessions": max_sessions},
        )
        response.raise_for_status()
        return [
            ClaimedLoginSessionPayload(
                session_id=item["id"],
                platform_account_id=item["platform_account_id"],
                profile_key=item["profile_key"],
                cdp_port=int(item["cdp_port"]),
                fresh_profile=bool(item.get("fresh_profile")),
            )
            for item in response.json().get("sessions", [])
            if item.get("cdp_port")
        ]

    async def report_login_progress(self, agent_id: str, session_id: str, status: str, *, error_message: str | None = None) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/agents/{agent_id}/login-sessions/{session_id}/progress",
            json={"status": status, "error_message": error_message},
        )
        response.raise_for_status()

    async def complete_login_session(
        self,
        agent_id: str,
        session_id: str,
        *,
        platform_nickname: str | None = None,
        platform_home_url: str | None = None,
    ) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/agents/{agent_id}/login-sessions/{session_id}/complete",
            json={"platform_nickname": platform_nickname, "platform_home_url": platform_home_url},
        )
        response.raise_for_status()

    async def fail_login_session(self, agent_id: str, session_id: str, error_message: str) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/agents/{agent_id}/login-sessions/{session_id}/fail",
            json={"error_message": error_message},
        )
        response.raise_for_status()

    async def claim_jobs(self, agent_id: str, supported_job_types: tuple[str, ...], max_jobs: int) -> list[ClaimedJobPayload]:
        response = await self._client.post(
            f"{self.base_url}/api/agents/{agent_id}/jobs/claim",
            json={"max_jobs": max_jobs, "supported_job_types": list(supported_job_types)},
        )
        response.raise_for_status()
        return [
            ClaimedJobPayload(
                job_id=item["job_id"],
                job_type=item["job_type"],
                account_id=item.get("account_id"),
                payload=item.get("payload") or {},
                checkpoint=item.get("checkpoint") or {},
            )
            for item in response.json().get("jobs", [])
        ]

    async def get_ready_session(self, account_id: str, agent_id: str) -> dict[str, Any]:
        response = await self._client.get(f"{self.base_url}/api/accounts/{account_id}/sessions/ready", params={"local_agent_id": agent_id})
        response.raise_for_status()
        return response.json().get("session_meta") or {}

    async def start_job(self, job_id: str, agent_id: str) -> None:
        response = await self._client.post(f"{self.base_url}/api/jobs/{job_id}/start", json={"agent_id": agent_id})
        response.raise_for_status()

    async def progress_job(self, job_id: str, agent_id: str, checkpoint: dict[str, Any], partial_metrics: dict[str, Any] | None = None) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/jobs/{job_id}/progress",
            json={"agent_id": agent_id, "checkpoint": checkpoint, "partial_metrics": partial_metrics or {}},
        )
        response.raise_for_status()

    async def complete_job(self, job_id: str, agent_id: str, status: str, result_summary: dict[str, Any]) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/jobs/{job_id}/complete",
            json={"agent_id": agent_id, "status": status, "result_summary": result_summary},
        )
        response.raise_for_status()

    async def fail_job(self, job_id: str, agent_id: str, failure: RuntimeFailure, checkpoint: dict[str, Any]) -> None:
        response = await self._client.post(
            f"{self.base_url}/api/jobs/{job_id}/fail",
            json={
                "agent_id": agent_id,
                "error": {
                    "code": failure.code.value,
                    "message": failure.message,
                    "retryable": failure.retryable,
                    "raw_context": failure.raw_context,
                },
                "checkpoint": checkpoint,
            },
        )
        response.raise_for_status()

    async def ingest_feed_candidates(self, payload: FeedCandidateIngestionRequest) -> dict[str, Any]:
        response = await self._client.post(f"{self.base_url}/api/ingestion/feed-candidates", json=payload.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()

    async def ingest_detail(self, payload: DetailIngestionRequest) -> dict[str, Any]:
        response = await self._client.post(f"{self.base_url}/api/ingestion/content-detail", json=payload.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()

    async def ingest_comments(self, payload: CommentIngestionRequest) -> dict[str, Any]:
        response = await self._client.post(f"{self.base_url}/api/ingestion/comments", json=payload.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()

    async def ingest_creator_monitor_items(self, payload: CreatorMonitorIngestionRequest) -> dict[str, Any]:
        response = await self._client.post(f"{self.base_url}/api/ingestion/creator-monitor-items", json=payload.model_dump(mode="json"))
        response.raise_for_status()
        return response.json()

    async def ingest_xhs_search_suggestions(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(f"{self.base_url}/api/ingestion/xhs-search-suggestions", json=payload)
        response.raise_for_status()
        return response.json()


class XhsJobExecutor:
    def __init__(self, *, client: CenterClient, config: AgentRuntimeConfig):
        self.client = client
        self.config = config

    async def execute(self, *, agent_id: str, job: ClaimedJobPayload) -> JobExecutionResult:
        if (job.payload.get("platform") or Platform.XHS.value) != Platform.XHS.value:
            return JobExecutionResult(status=JobStatus.PARTIAL_SUCCESS.value, result_summary={"unsupported_platform": job.payload.get("platform")})
        session_meta = await self._session_meta(agent_id=agent_id, account_id=job.account_id)
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY:
            await session.close()
            raise RuntimeFailure(_session_error_code(session.status), session.message or f"session status: {session.status.value}", retryable=True)
        try:
            if job.job_type == JobType.FEED_COLLECT.value:
                return await self._run_feed(job, session.page)
            if job.job_type == JobType.DETAIL_FETCH.value:
                return await self._run_detail(job, session.page)
            if job.job_type == JobType.COMMENT_FETCH.value:
                return await self._run_comment(job, session.page)
            if job.job_type == JobType.CREATOR_MONITOR.value:
                return await self._run_creator_monitor(job, session.page)
            if job.job_type == JobType.SEARCH_COLLECT.value:
                return await self._run_search_collect(job, session.page)
            if job.job_type == JobType.XHS_SEARCH_SUGGEST.value:
                return await self._run_search_suggest(job, session.page)
            return JobExecutionResult(status=JobStatus.PARTIAL_SUCCESS.value, result_summary={"unsupported_job_type": job.job_type})
        finally:
            await session.close()

    async def _session_meta(self, *, agent_id: str, account_id: str | None) -> dict[str, Any]:
        if account_id and account_id in self.config.account_sessions:
            return self._resolve_session_meta(self.config.account_sessions[account_id])
        if account_id:
            try:
                meta = await self.client.get_ready_session(account_id, agent_id)
                if meta:
                    return self._resolve_session_meta(meta)
            except httpx.HTTPStatusError:
                pass
        if self.config.cdp_url:
            return {"cdp_url": self.config.cdp_url}
        raise RuntimeFailure(ErrorCode.SESSION_CONNECT_FAILED, "no ready account session and no fallback cdp_url", retryable=True)

    def _resolve_session_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(meta)
        profile_key = resolved.get("profile_key")
        if profile_key and not resolved.get("user_data_dir") and not resolved.get("profile_ref"):
            from pathlib import Path

            from local_agent_runtime.chrome_launcher import resolve_profile_dir

            root = Path(self.config.project_root or Path.cwd())
            resolved["user_data_dir"] = str(resolve_profile_dir(root, str(profile_key)))
        elif profile_key and resolved.get("profile_ref") and not str(resolved.get("profile_ref")).startswith(str(Path.cwd())):
            from pathlib import Path

            from local_agent_runtime.chrome_launcher import resolve_profile_dir

            root = Path(self.config.project_root or Path.cwd())
            resolved["user_data_dir"] = str(resolve_profile_dir(root, str(profile_key)))
        return resolved

    async def _run_search_collect(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        keywords = payload.get("keywords") or []
        max_items = int(payload.get("max_items") or 50)
        candidates, report = await XhsSearchProbe(
            keywords=keywords,
            max_items=max_items,
            search_sort=str(payload.get("search_sort") or "comprehensive"),
            note_type=str(payload.get("note_type") or "all"),
            publish_time=str(payload.get("publish_time") or "all"),
            search_scope=str(payload.get("search_scope") or "all"),
            location_filter=str(payload.get("location_filter") or "all"),
        ).collect(page)
        ingestion = await self.client.ingest_feed_candidates(
            FeedCandidateIngestionRequest(job_id=job.job_id, account_id=job.account_id, candidates=candidates)
        )
        results = ingestion.get("results") or []
        new_count = sum(1 for item in results if item.get("is_new_content"))
        detail_jobs = sum(1 for item in results if item.get("detail_job_enqueued"))
        ingestion_total = len(results)
        duplicate_count = max(0, ingestion_total - new_count)
        return JobExecutionResult(
            status=JobStatus.SUCCESS.value,
            checkpoint={"items_seen": len(candidates), "keywords": keywords},
            result_summary={
                **report,
                "ingestion_success_count": ingestion_total,
                "new_content_count": new_count,
                "duplicate_content_count": duplicate_count,
                "detail_jobs_enqueued": detail_jobs,
                "prelim_candidate_count": ingestion_total,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(capability_key="xhs.search.notes", surface="search", report=report),
            },
        )

    async def _run_search_suggest(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        core_keyword = str(payload.get("core_keyword") or "").strip()
        items, report = await XhsSearchSuggestProbe(core_keyword=core_keyword).collect(page)
        if hasattr(self.client, "ingest_xhs_search_suggestions"):
            await self.client.ingest_xhs_search_suggestions(
                {
                    "job_id": job.job_id,
                    "account_id": job.account_id,
                    "core_keyword": core_keyword,
                    "items": items,
                }
            )
        return JobExecutionResult(
            status=JobStatus.SUCCESS.value,
            result_summary={
                **report,
                "core_keyword": core_keyword,
                "suggestion_count": len(items),
                "runtime": "local_agent_runtime_v1",
            },
        )

    async def _run_feed(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        target_count = int(job.payload.get("target_count") or 50)
        candidates, report = await XhsHomeFeedProbe(target_count=target_count).collect(page)
        ingestion = await self.client.ingest_feed_candidates(
            FeedCandidateIngestionRequest(job_id=job.job_id, account_id=job.account_id, candidates=candidates)
        )
        results = ingestion.get("results") or []
        prelim_scored = [item for item in results if item.get("feed_prelim_pass") is not None]
        prelim_pass_count = sum(1 for item in prelim_scored if item.get("feed_prelim_pass"))
        missing_like_ids = {
            item.platform_content_id
            for item in candidates
            if item.visible_like_count is None
        }
        missing_like_detail_jobs = sum(
            1
            for item in results
            if item.get("detail_job_enqueued") and item.get("platform_content_id") in missing_like_ids
        )
        return JobExecutionResult(
            status=JobStatus.SUCCESS.value,
            checkpoint={"items_seen": len(candidates)},
            result_summary={
                **report,
                "raw_items_seen": len(candidates),
                "items_seen": len(candidates),
                "normalized_items": len(candidates),
                "ingestion_success_count": len(results),
                "unique_contents_inserted": sum(1 for item in results if item.get("is_new_content")),
                "duplicate_contents": max(0, len(results) - sum(1 for item in results if item.get("is_new_content"))),
                "prelim_pass_count": prelim_pass_count,
                "prelim_discard_count": max(0, len(prelim_scored) - prelim_pass_count),
                "detail_jobs_enqueued": sum(1 for item in results if item.get("detail_job_enqueued")),
                "missing_visible_like_count": len(missing_like_ids),
                "missing_visible_like_detail_jobs_enqueued": missing_like_detail_jobs,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(capability_key="xhs.feed.home_recommend", surface="homefeed", report=report),
            },
        )

    async def _run_detail(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        snapshot = await XhsDetailProbe().fetch_detail(
            page,
            canonical_url=payload.get("canonical_url"),
            platform_content_id=payload.get("platform_content_id"),
            platform_context=payload.get("platform_context") or {},
        )
        snapshot = await attach_cover_bytes(page, snapshot)
        ingestion = await self.client.ingest_detail(DetailIngestionRequest(job_id=job.job_id, content_id=payload["content_id"], snapshot=snapshot))
        return JobExecutionResult(
            status=JobStatus.SUCCESS.value,
            checkpoint={"snapshot_id": ingestion.get("snapshot_id")},
            result_summary={
                "snapshot_id": ingestion.get("snapshot_id"),
                "comment_job_enqueued": ingestion.get("comment_job_enqueued"),
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(
                    capability_key="xhs.note.detail",
                    surface="detail",
                    report=(snapshot.raw_payload or {}).get("dom_fallback") or {},
                ),
            },
        )

    async def _run_comment(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        result = await XhsCommentProbe().fetch_comments_result(
            page,
            canonical_url=payload.get("canonical_url"),
            platform_content_id=payload.get("platform_content_id"),
            platform_context=payload.get("platform_context") or {},
            limit=int(payload.get("max_comments") or 20),
        )
        if result.surface_status == "comment_surface_unavailable":
            return JobExecutionResult(
                status=JobStatus.PARTIAL_SUCCESS.value,
                result_summary={
                    "error_code": ErrorCode.COMMENT_SURFACE_UNAVAILABLE.value,
                    "surface_status": result.surface_status,
                    "message": result.message,
                    "diagnostics": result.diagnostics,
                    "runtime": "local_agent_runtime_v1",
                    "engine_audit": engine_audit_summary(
                        capability_key="xhs.note.comments",
                        surface="comment",
                        report=result.diagnostics,
                        issue_codes=[result.surface_status],
                    ),
                },
            )
        if result.surface_status == "missing_xsec_context":
            raise RuntimeFailure(ErrorCode.MISSING_XSEC_CONTEXT, result.message or "missing xsec context", raw_context=result.diagnostics)
        if result.surface_status in {"manual_verify_required", "login_required"}:
            raise RuntimeFailure(result.error_code or ErrorCode.SESSION_EXPIRED, result.message or result.surface_status, raw_context=result.diagnostics)
        ingestion = await self.client.ingest_comments(CommentIngestionRequest(job_id=job.job_id, content_id=payload["content_id"], comments=result.comments))
        return JobExecutionResult(
            status=JobStatus.SUCCESS.value,
            checkpoint={"comments_seen": len(result.comments)},
            result_summary={
                "comments_inserted": ingestion.get("inserted"),
                "comments_updated": ingestion.get("updated"),
                "lead_keyword_hits": ingestion.get("lead_keyword_hits"),
                "surface_status": result.surface_status,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(capability_key="xhs.note.comments", surface="comment", report=result.diagnostics),
            },
        )

    async def _run_creator_monitor(self, job: ClaimedJobPayload, page) -> JobExecutionResult:
        payload = job.payload
        try:
            fetch_result = await XhsCreatorConnector().fetch_latest(
                page,
                creator_profile_url=payload.get("creator_profile_url"),
                creator_platform_id=payload.get("creator_platform_id"),
                context=payload.get("platform_context") or {},
                limit=int(payload.get("max_latest_items") or 20),
            )
        except ValueError as exc:
            raise RuntimeFailure(
                ErrorCode.NON_RETRYABLE_PLATFORM_ERROR,
                str(exc),
                raw_context={
                    "source_path": "creator_profile_context",
                    "creator_profile_url": payload.get("creator_profile_url"),
                    "creator_platform_id": payload.get("creator_platform_id"),
                },
            ) from exc
        except XhsCreatorFetchError as exc:
            raise RuntimeFailure(
                ErrorCode(exc.error_code),
                str(exc),
                retryable=exc.retryable,
                raw_context=exc.raw_context,
            ) from exc
        candidates = [item.to_candidate(feed_position=index) for index, item in enumerate(fetch_result.items, start=1)]
        ingestion = await self.client.ingest_creator_monitor_items(
            CreatorMonitorIngestionRequest(
                job_id=job.job_id,
                account_id=job.account_id,
                creator_monitor_id=payload["creator_monitor_id"],
                creator_display_name=fetch_result.creator_display_name,
                items=candidates,
                raw_payload=fetch_result.raw_payload,
            )
        )
        return JobExecutionResult(
            status=JobStatus.SUCCESS.value,
            checkpoint={"items_seen": ingestion.get("items_seen")},
            result_summary={
                **ingestion,
                "runtime": "local_agent_runtime_v1",
                "engine_audit": engine_audit_summary(
                    capability_key="xhs.creator.posted_notes",
                    surface="creator",
                    report={
                        "source_path": "creator_user_posted",
                        "field_coverage": {},
                        "perf": {},
                    },
                ),
            },
        )


class LocalAgentRuntime:
    def __init__(
        self,
        *,
        config: AgentRuntimeConfig,
        client: CenterClientProtocol | None = None,
        executor: Any | None = None,
        login_executor: Any | None = None,
    ):
        self.config = config
        self.client = client or CenterClient(base_url=config.center_base_url)
        self.agent_id = config.agent_id
        self.executor = executor
        self.login_executor = login_executor
        self.running_job_ids: set[str] = set()
        self._last_heartbeat_at = 0.0
        self._registered_this_process = False

    async def ensure_registered(self) -> str:
        if not self._registered_this_process:
            self.agent_id = await self.client.register_agent(self.config)
            self.config = replace(self.config, agent_id=self.agent_id)
            self._registered_this_process = True
        return self.agent_id

    async def run_forever(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.config.poll_interval_seconds)

    async def run_once(self) -> int:
        agent_id = await self.ensure_registered()
        await self._heartbeat_if_due(agent_id)
        handled = 0
        if self.config.supports_account_login:
            handled += await self._handle_login_sessions(agent_id)
        jobs = await self.client.claim_jobs(agent_id, self.config.supported_job_types, self.config.max_jobs_per_claim)
        for job in jobs:
            await self._handle_job(agent_id, job)
        return handled + len(jobs)

    async def _handle_login_sessions(self, agent_id: str) -> int:
        sessions = await self.client.claim_login_sessions(agent_id, max_sessions=1)
        if not sessions:
            return 0
        logging.getLogger("local_agent").info(
            "Claimed %s login session(s): %s",
            len(sessions),
            ", ".join(f"{item.session_id[:8]}… account={item.platform_account_id[:8]}…" for item in sessions),
        )
        from pathlib import Path

        from local_agent_runtime.account_login_executor import AccountLoginExecutor, LoginSessionPayload

        project_root = Path(self.config.project_root or Path.cwd())
        login_executor = self.login_executor or AccountLoginExecutor(project_root=project_root, client=self.client)
        for session in sessions:
            await login_executor.execute(
                agent_id=agent_id,
                session=LoginSessionPayload(
                    session_id=session.session_id,
                    platform_account_id=session.platform_account_id,
                    profile_key=session.profile_key,
                    cdp_port=session.cdp_port,
                    fresh_profile=session.fresh_profile,
                ),
            )
        return len(sessions)

    async def _heartbeat_if_due(self, agent_id: str) -> None:
        now = time.monotonic()
        if self._last_heartbeat_at and now - self._last_heartbeat_at < self.config.heartbeat_interval_seconds:
            return
        await self.client.heartbeat(
            agent_id,
            sorted(self.running_job_ids),
            capabilities=build_agent_capabilities_payload(self.config),
            agent_version=self.config.agent_version,
        )
        self._last_heartbeat_at = now
        logging.getLogger("local_agent").info(
            "Heartbeat OK agent_id=%s device=%s",
            agent_id,
            self.config.device_name,
        )

    async def mark_offline(self, agent_id: str) -> None:
        await self.client.heartbeat(agent_id, [], status="offline")

    async def _handle_job(self, agent_id: str, job: ClaimedJobPayload) -> None:
        self.running_job_ids.add(job.job_id)
        executor = self.executor or XhsJobExecutor(client=self.client, config=self.config)
        try:
            await self.client.start_job(job.job_id, agent_id)
            result = await executor.execute(agent_id=agent_id, job=job)
            if result.checkpoint:
                await self.client.progress_job(job.job_id, agent_id, result.checkpoint, result.result_summary)
            await self.client.complete_job(job.job_id, agent_id, result.status, result.result_summary)
        except RuntimeFailure as exc:
            await self.client.fail_job(job.job_id, agent_id, exc, job.checkpoint)
        except Exception as exc:
            failure = RuntimeFailure(ErrorCode.INTERNAL_ENGINE_ERROR, str(exc), retryable=True)
            await self.client.fail_job(job.job_id, agent_id, failure, job.checkpoint)
        finally:
            self.running_job_ids.discard(job.job_id)


def _session_error_code(status: SessionStatus) -> ErrorCode:
    if status == SessionStatus.MANUAL_VERIFY_REQUIRED:
        return ErrorCode.MANUAL_VERIFY_REQUIRED
    if status == SessionStatus.EXPIRED:
        return ErrorCode.SESSION_EXPIRED
    return ErrorCode.SESSION_CONNECT_FAILED
