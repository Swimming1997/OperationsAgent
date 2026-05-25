# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from local_agent_runtime.connectors.xhs.normalizer import extract_xhs_content_id
from local_agent_runtime.connectors.xhs.context import context_from_url_and_raw, merge_xhs_context, normalize_xhs_url
from intelligence_engine.db.models import ContentIdentity
from local_agent_runtime.enums import ContentType, JobType, Platform
from intelligence_engine.local_agent.xhs_comment_probe_runner import XhsCommentProbeRunner
from intelligence_engine.storage.repositories.job_repository import JobRepository


class XhsManualCommentProbeRunner:
    def __init__(self, *, db: Session, center_base_url: str = "http://127.0.0.1:8000"):
        self.db = db
        self.center_base_url = center_base_url

    def _normalize_url(self, url: str) -> str:
        normalized = normalize_xhs_url(url)
        if not normalized:
            raise ValueError(f"empty xhs url: {url}")
        return normalized

    def _ensure_content_and_job(self, *, url: str, max_comments: int) -> tuple[ContentIdentity, str]:
        canonical_url = self._normalize_url(url)
        platform_context = context_from_url_and_raw(canonical_url)
        platform_content_id = extract_xhs_content_id(canonical_url) or platform_context.get("note_id")
        if not platform_content_id:
            raise ValueError(f"cannot extract XHS content id from url: {url}")
        if not platform_context.get("has_xsec_context"):
            raise ValueError(f"missing_xsec_context: full XHS note URL with xsec_token and xsec_source is required: {url}")
        content = self.db.scalar(
            select(ContentIdentity).where(
                ContentIdentity.platform == Platform.XHS.value,
                ContentIdentity.platform_content_id == platform_content_id,
            )
        )
        now = datetime.now(timezone.utc)
        if not content:
            content = ContentIdentity(
                platform=Platform.XHS.value,
                platform_content_id=platform_content_id,
                canonical_url=canonical_url,
                content_type=ContentType.UNKNOWN.value,
                first_seen_at=now,
                last_seen_at=now,
                metadata_json={
                    "manual_comment_probe": True,
                    "platform_context": merge_xhs_context(platform_context),
                },
            )
            self.db.add(content)
            self.db.flush()
        else:
            content.canonical_url = canonical_url
            metadata = dict(content.metadata_json or {})
            metadata["platform_context"] = merge_xhs_context(
                metadata.get("platform_context") if isinstance(metadata.get("platform_context"), dict) else None,
                platform_context,
            )
            content.metadata_json = metadata
            content.last_seen_at = now
        job = JobRepository(self.db).create_job(
            job_type=JobType.COMMENT_FETCH,
            payload={
                "content_id": content.id,
                "platform": Platform.XHS.value,
                "platform_content_id": platform_content_id,
                "canonical_url": canonical_url,
                "platform_context": merge_xhs_context(platform_context),
                "max_comments": max_comments,
                "include_sub_comments": False,
                "manual_url_probe": True,
            },
            priority=50,
        )
        return content, job.id

    async def run(self, *, urls: list[str], session_meta: dict, max_comments: int = 20, post_ingestion: bool = True) -> dict:
        prepared = []
        prepare_failures = []
        for url in urls:
            try:
                content, job_id = self._ensure_content_and_job(url=url, max_comments=max_comments)
                prepared.append({"url": url, "content_id": content.id, "job_id": job_id})
            except ValueError as exc:
                prepare_failures.append({"url": url, "error": str(exc)})
        self.db.commit()
        result = await XhsCommentProbeRunner(db=self.db, center_base_url=self.center_base_url).run(
            session_meta=session_meta,
            limit=len(prepared),
            max_comments=max_comments,
            post_ingestion=post_ingestion,
        ) if prepared else {
            "selected_job_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "comment_snapshot_count": 0,
            "field_report": {"total": 0, "field_success": {}},
            "keyword_hits": [],
            "comment_surface_unavailable_urls": [],
            "successes": [],
            "failures": [],
        }
        result["selected_url_count"] = len(urls)
        result["prepared_urls"] = prepared
        result["prepare_failures"] = prepare_failures
        result["failed_count"] = int(result.get("failed_count") or 0) + len(prepare_failures)
        return result
