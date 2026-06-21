from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from local_agent_runtime.connectors.douyin.comment_probe import DouyinCommentProbe
from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe
from local_agent_runtime.connectors.xhs.detail_probe import XhsDetailProbe
from local_agent_runtime.contracts import DetailIngestionRequest
from local_agent_runtime.enums import Platform, SessionStatus
from local_agent_runtime.runtime import AgentRuntimeConfig
from local_agent_runtime.sessions.registry import default_session_registry
from local_agent_runtime.storage.repository import (
    DEFAULT_ACQUISITION_KEYWORDS,
    LocalIntelligenceRepository,
)

logger = logging.getLogger("local_agent.detail_batch")


class CentralWorkspaceSession:
    def __init__(self, *, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.access_token: str | None = None
        self.user: dict[str, Any] | None = None

    def set_base_url(self, base_url: str) -> None:
        self.base_url = _normalize_center_url(base_url)
        self.logout()

    async def login(self, *, username: str, password: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
            )
            response.raise_for_status()
            payload = response.json()
        roles = set(payload.get("user", {}).get("roles") or [])
        if not roles.intersection({"admin", "supervisor", "operator"}):
            raise PermissionError("current user cannot write reference library")
        self.access_token = payload["access_token"]
        self.user = payload["user"]
        return self.status()

    def logout(self) -> None:
        self.access_token = None
        self.user = None

    def status(self) -> dict[str, Any]:
        return {
            "authenticated": bool(self.access_token),
            "user": self.user,
            "center_url": self.base_url,
        }

    async def promote_content(
        self,
        *,
        candidate: dict[str, Any],
        detail: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.access_token:
            raise PermissionError("central login required")
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/api/intelligence/contents/promote",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"candidate": candidate, "detail": detail},
            )
            if response.status_code == 401:
                self.logout()
            response.raise_for_status()
            return response.json()

    async def create_reference_library_item(
        self,
        *,
        central_content_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.access_token:
            raise PermissionError("central login required")
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/api/intelligence/contents/{central_content_id}/reference-library-items",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=payload,
            )
            if response.status_code == 401:
                self.logout()
            response.raise_for_status()
            return response.json()


class LocalContentActionService:
    CENTER_URL_SETTING = "central_server_url"

    def __init__(
        self,
        *,
        config: AgentRuntimeConfig,
        repository: LocalIntelligenceRepository,
        central_session: CentralWorkspaceSession | None = None,
        account_sessions_provider: Callable[[], list[dict[str, Any]]] | None = None,
    ):
        self.config = config
        self.repository = repository
        # Returns the logged-in local accounts available for collection, each as
        # {"account_id": ..., "cdp_url": ..., "label": ...}. Drives multi-account
        # parallel detail/comment fetching (concurrency = number of accounts).
        self.account_sessions_provider = account_sessions_provider
        saved_center_url = repository.get_setting(
            self.CENTER_URL_SETTING,
            config.center_base_url,
        ) or config.center_base_url
        self.central_session = central_session or CentralWorkspaceSession(base_url=saved_center_url)
        self.center_url = _normalize_center_url(saved_center_url)
        if hasattr(self.central_session, "set_base_url"):
            self.central_session.set_base_url(self.center_url)
        self._running_content_ids: set[int] = set()

    def submit_acquisition_check(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        content_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if content_id in self._running_content_ids:
            return {"content_id": content_id, "status": "running"}
        content = self.repository.get_content_detail(content_id)
        if not content:
            raise ValueError("content not found")
        keywords = [
            str(item).strip()
            for item in (payload.get("keywords") or DEFAULT_ACQUISITION_KEYWORDS)
            if str(item).strip()
        ]
        max_comments = max(1, min(int(payload.get("max_comments") or 30), 100))
        task_id = self.repository.create_collect_task(
            task_type="acquisition_check",
            target=str(content_id),
            params={"keywords": keywords, "max_comments": max_comments},
        )
        self._running_content_ids.add(content_id)
        future = asyncio.run_coroutine_threadsafe(
            self._check_acquisition(
                task_id=task_id,
                content=content,
                keywords=keywords,
                max_comments=max_comments,
            ),
            loop,
        )
        future.add_done_callback(
            lambda completed, item_id=content_id: self._action_done(item_id, completed)
        )
        return {"task_id": task_id, "content_id": content_id, "status": "queued"}

    def submit_detail_fetch(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        content_id: int,
    ) -> dict[str, Any]:
        if content_id in self._running_content_ids:
            return {"content_id": content_id, "status": "running"}
        content = self.repository.get_content_detail(content_id)
        if not content:
            raise ValueError("content not found")
        task_id = self.repository.create_collect_task(
            task_type="detail_fetch",
            target=str(content_id),
            params={},
        )
        self._running_content_ids.add(content_id)
        future = asyncio.run_coroutine_threadsafe(
            self._fetch_detail(task_id=task_id, content=content),
            loop,
        )
        future.add_done_callback(
            lambda completed, item_id=content_id: self._action_done(item_id, completed)
        )
        return {"task_id": task_id, "content_id": content_id, "status": "queued"}

    def submit_detail_batch(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        content_ids = [int(item) for item in (payload.get("content_ids") or []) if int(item) > 0]
        max_comments = max(1, min(int(payload.get("max_comments") or 30), 200))
        targets = self.repository.list_pending_detail_contents(
            platform=Platform.XHS.value,
            content_ids=content_ids or None,
            limit=500,
        )
        if not targets:
            return {"status": "empty", "target_count": 0, "worker_count": 0}
        sessions = self._resolve_batch_sessions(payload.get("account_ids"))
        if not sessions:
            raise RuntimeError("没有可用的采集账号，请先在“账号管理”里登录账号，或配置默认浏览器")
        task_id = self.repository.create_collect_task(
            task_type="detail_batch",
            target=f"{len(targets)} 条笔记",
            params={
                "content_ids": [int(item["id"]) for item in targets],
                "max_comments": max_comments,
                "worker_count": len(sessions),
            },
        )
        asyncio.run_coroutine_threadsafe(
            self._run_detail_batch(
                task_id=task_id,
                targets=targets,
                sessions=sessions,
                max_comments=max_comments,
            ),
            loop,
        )
        return {
            "task_id": task_id,
            "status": "queued",
            "target_count": len(targets),
            "worker_count": len(sessions),
        }

    def _resolve_batch_sessions(self, account_ids: Any) -> list[dict[str, Any]]:
        wanted = {str(item).strip() for item in (account_ids or []) if str(item).strip()}
        sessions: list[dict[str, Any]] = []
        # Dedupe by cdp_url: two account records pointing at the same browser must
        # not spawn two workers, or they would drive the same tab and clobber each
        # other (defeating concurrency). One distinct browser = one worker.
        seen_cdp: set[str] = set()
        if self.account_sessions_provider is not None:
            for item in self.account_sessions_provider() or []:
                cdp_url = str(item.get("cdp_url") or "").strip()
                if not cdp_url or cdp_url in seen_cdp:
                    continue
                account_id = str(item.get("account_id") or "").strip() or None
                if wanted and (account_id or "") not in wanted:
                    continue
                seen_cdp.add(cdp_url)
                sessions.append(
                    {"account_id": account_id, "cdp_url": cdp_url, "label": item.get("label")}
                )
        if not sessions and not wanted and self.config.cdp_url:
            sessions.append({"account_id": None, "cdp_url": self.config.cdp_url, "label": "默认浏览器"})
        logger.info(
            "detail-batch resolved %d session(s): %s",
            len(sessions),
            [
                {"account_id": s["account_id"], "label": s["label"], "cdp_url": s["cdp_url"]}
                for s in sessions
            ],
        )
        return sessions

    async def _run_detail_batch(
        self,
        *,
        task_id: int,
        targets: list[dict[str, Any]],
        sessions: list[dict[str, Any]],
        max_comments: int,
    ) -> None:
        run_id = f"local-detail-batch-{task_id}-{uuid.uuid4().hex[:8]}"
        self.repository.mark_collect_task_running(task_id)
        self.repository.start_local_collect_run(
            task_id=task_id, run_id=run_id, job_type="detail_batch"
        )
        queue: asyncio.Queue = asyncio.Queue()
        for target in targets:
            queue.put_nowait(target)
        counters = {"done": 0, "failed": 0, "comments": 0, "workers": len(sessions)}
        progress_lock = asyncio.Lock()
        logger.info(
            "detail-batch START task_id=%s run_id=%s targets=%d workers=%d max_comments=%d",
            task_id,
            run_id,
            len(targets),
            len(sessions),
            max_comments,
        )

        async def record_progress() -> None:
            # Persist progress per item so the UI can poll it (real-time feedback §8.1).
            async with progress_lock:
                self.repository.update_collect_run_progress(
                    central_job_id=run_id,
                    item_count=counters["done"],
                    error_summary=dict(counters),
                )

        async def worker(session_meta: dict[str, Any]) -> None:
            label = session_meta.get("label") or session_meta.get("account_id") or "默认浏览器"
            session = None
            try:
                session = await default_session_registry.create(Platform.XHS.value).acquire(
                    session_meta={"cdp_url": session_meta["cdp_url"]}
                )
                if session.status != SessionStatus.READY:
                    logger.warning(
                        "detail-batch worker[%s] session not ready: status=%s message=%s",
                        label,
                        getattr(session, "status", None),
                        getattr(session, "message", None),
                    )
                    return
                logger.info("detail-batch worker[%s] ready, start consuming queue", label)
                while True:
                    try:
                        target = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    content_id = target.get("id")
                    try:
                        await self._process_detail_target(
                            page=session.page,
                            target=target,
                            run_id=run_id,
                            max_comments=max_comments,
                            counters=counters,
                        )
                        counters["done"] += 1
                        logger.debug(
                            "detail-batch worker[%s] done content_id=%s (%d/%d)",
                            label,
                            content_id,
                            counters["done"],
                            len(targets),
                        )
                    except Exception as exc:
                        counters["failed"] += 1
                        logger.warning(
                            "detail-batch worker[%s] failed content_id=%s: %s",
                            label,
                            content_id,
                            exc,
                        )
                    finally:
                        await record_progress()
                        queue.task_done()
            finally:
                if session is not None:
                    await session.close()

        try:
            await asyncio.gather(*(worker(meta) for meta in sessions))
            logger.info(
                "detail-batch DONE task_id=%s done=%d failed=%d comments=%d",
                task_id,
                counters["done"],
                counters["failed"],
                counters["comments"],
            )
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="success",
                item_count=counters["done"],
                error_summary=counters,
            )
            self.repository.finish_collect_task(task_id, success=True)
        except Exception as exc:
            logger.error("detail-batch FAILED task_id=%s: %s", task_id, exc, exc_info=True)
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="failed",
                item_count=counters["done"],
                error_summary={"message": str(exc), **counters},
            )
            self.repository.finish_collect_task(task_id, success=False)

    async def _process_detail_target(
        self,
        *,
        page,
        target: dict[str, Any],
        run_id: str,
        max_comments: int,
        counters: dict[str, int],
    ) -> None:
        content_id = int(target["id"])
        content = self.repository.get_content_detail(content_id)
        if not content:
            return
        platform_content_id = content["platform_content_id"]
        canonical_url = content.get("canonical_url") or ""
        platform_context = content.get("platform_context") or {}
        if not content.get("detail_fetched_at"):
            snapshot = await XhsDetailProbe().fetch_detail(
                page,
                canonical_url=canonical_url,
                platform_content_id=platform_content_id,
                platform_context=platform_context,
                source_surface="search",
                upstream_author_name=content.get("author_name"),
            )
            snapshot = snapshot.model_copy(
                update={
                    "raw_payload": {
                        **(snapshot.raw_payload or {}),
                        "platform_content_id": platform_content_id,
                    }
                }
            )
            self.repository.upsert_detail(
                DetailIngestionRequest(
                    job_id=run_id,
                    content_id=content.get("central_content_id") or platform_content_id,
                    snapshot=snapshot,
                )
            )
        result = await XhsCommentProbe().fetch_comments_result(
            page,
            canonical_url=canonical_url,
            platform_content_id=platform_content_id,
            platform_context=platform_context,
            limit=max_comments,
        )
        if result.surface_status in {"ok", "true_empty_comments"}:
            saved = self.repository.upsert_comments_full(
                content_id=content_id,
                comments=result.comments,
                replace=True,
            )
            counters["comments"] += int(saved.get("stored", 0))

    async def _fetch_detail(self, *, task_id: int, content: dict[str, Any]) -> None:
        run_id = f"local-detail-{task_id}-{uuid.uuid4().hex[:8]}"
        self.repository.mark_collect_task_running(task_id)
        self.repository.start_local_collect_run(
            task_id=task_id,
            run_id=run_id,
            job_type="detail_fetch",
        )
        session = None
        try:
            session = await default_session_registry.create(str(content["platform"])).acquire(
                session_meta=self._session_meta(None)
            )
            if session.status != SessionStatus.READY:
                raise RuntimeError(session.message or f"session status: {session.status}")
            if str(content["platform"]) != Platform.XHS.value:
                raise ValueError(f"unsupported platform: {content['platform']}")
            snapshot = await XhsDetailProbe().fetch_detail(
                session.page,
                canonical_url=content.get("canonical_url") or "",
                platform_content_id=content["platform_content_id"],
                platform_context=content.get("platform_context") or {},
                source_surface="search",
                upstream_author_name=content.get("author_name"),
            )
            snapshot = snapshot.model_copy(
                update={
                    "raw_payload": {
                        **(snapshot.raw_payload or {}),
                        "platform_content_id": content["platform_content_id"],
                    }
                }
            )
            self.repository.upsert_detail(
                DetailIngestionRequest(
                    job_id=run_id,
                    content_id=content.get("central_content_id") or content["platform_content_id"],
                    snapshot=snapshot,
                )
            )
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="success",
                item_count=1,
            )
            self.repository.finish_collect_task(task_id, success=True)
        except Exception as exc:
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            self.repository.finish_collect_task(task_id, success=False)
        finally:
            if session is not None:
                await session.close()

    async def _check_acquisition(
        self,
        *,
        task_id: int,
        content: dict[str, Any],
        keywords: list[str],
        max_comments: int,
    ) -> None:
        run_id = f"local-acquisition-{task_id}-{uuid.uuid4().hex[:8]}"
        self.repository.mark_collect_task_running(task_id)
        self.repository.start_local_collect_run(
            task_id=task_id,
            run_id=run_id,
            job_type="comment_fetch",
        )
        session = None
        try:
            platform = str(content["platform"])
            session = await default_session_registry.create(platform).acquire(
                session_meta=self._session_meta(None)
            )
            if session.status != SessionStatus.READY:
                raise RuntimeError(session.message or f"session status: {session.status}")
            if platform == Platform.XHS.value:
                result = await XhsCommentProbe().fetch_comments_result(
                    session.page,
                    canonical_url=content.get("canonical_url") or "",
                    platform_content_id=content["platform_content_id"],
                    platform_context=content.get("platform_context") or {},
                    limit=max_comments,
                )
            elif platform == Platform.DOUYIN.value:
                result = await DouyinCommentProbe().fetch_comments_result(
                    session.page,
                    canonical_url=content.get("canonical_url"),
                    platform_content_id=content["platform_content_id"],
                    limit=max_comments,
                )
            else:
                raise ValueError(f"unsupported platform: {platform}")
            if result.surface_status not in {"ok", "true_empty_comments"}:
                raise RuntimeError(result.message or result.surface_status)
            saved = self.repository.upsert_local_comment_hits(
                content_id=int(content["id"]),
                comments=result.comments,
                keywords=keywords,
                replace=True,
            )
            refreshed = self.repository.get_content_detail(int(content["id"])) or {}
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="success",
                item_count=len(result.comments),
                error_summary={
                    "surface_status": result.surface_status,
                    "matched_comment_count": refreshed.get("acquisition_hit_count", 0),
                    **saved,
                },
            )
            self.repository.finish_collect_task(task_id, success=True)
        except Exception as exc:
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="failed",
                error_summary={"message": str(exc)},
            )
            self.repository.finish_collect_task(task_id, success=False)
        finally:
            if session is not None:
                await session.close()

    async def login_central(self, payload: dict[str, Any]) -> dict[str, Any]:
        center_url = _normalize_center_url(
            str(payload.get("center_url") or self.center_url)
        )
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if not username or not password:
            raise ValueError("username and password are required")
        if hasattr(self.central_session, "set_base_url"):
            self.central_session.set_base_url(center_url)
        status = await self.central_session.login(username=username, password=password)
        self.center_url = center_url
        self.repository.set_setting(self.CENTER_URL_SETTING, center_url)
        retry = await self.retry_pending_materials()
        return {**status, "center_url": center_url, "retry": retry}

    def logout_central(self) -> dict[str, Any]:
        self.central_session.logout()
        return self.central_session.status()

    def central_status(self) -> dict[str, Any]:
        return {
            **self.central_session.status(),
            "center_url": self.center_url,
        }

    async def add_to_material_library(
        self,
        *,
        content_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        export = self.repository.queue_material_export(
            content_id=content_id,
            library_type=str(payload.get("library_type") or "uncategorized"),
            rating=str(payload.get("rating") or "").strip() or None,
            material_tags=[
                str(item).strip()
                for item in (payload.get("material_tags") or [])
                if str(item).strip()
            ],
            note=str(payload.get("note") or "").strip() or None,
            selected_reason=str(payload.get("selected_reason") or "").strip() or None,
        )
        return await self._sync_material_export(export)

    async def retry_pending_materials(self) -> dict[str, int]:
        synced = 0
        failed = 0
        for export in self.repository.list_pending_material_exports(limit=20):
            result = await self._sync_material_export(export)
            if result["status"] == "synced":
                synced += 1
            else:
                failed += 1
        return {"synced": synced, "failed": failed}

    async def _sync_material_export(self, export: dict[str, Any]) -> dict[str, Any]:
        content_id = int(export["content_id"])
        central_content_id = export.get("central_content_id")
        if not central_content_id:
            # Local-first: the content only lives locally, so push (promote) this
            # selected content into central first to obtain its central content id,
            # then build the material entry against it.
            try:
                central_content_id = await self._promote_content(content_id)
            except Exception as exc:
                self.repository.mark_material_export_failed(content_id=content_id, error=str(exc))
                return {"content_id": content_id, "status": "failed", "error": str(exc)}
        try:
            response = await self.central_session.create_reference_library_item(
                central_content_id=central_content_id,
                payload={
                    "library_type": export["library_type"],
                    "selection_sources": ["manual"],
                    "selected_reason": export.get("selected_reason"),
                    "rating": export.get("rating"),
                    "matched_keywords": self._matched_keywords(content_id),
                    "material_tags": export.get("material_tags") or [],
                    "note": export.get("note"),
                    "metadata": {"source": "local_first_workspace"},
                },
            )
        except Exception as exc:
            self.repository.mark_material_export_failed(
                content_id=content_id,
                error=str(exc),
            )
            return {"content_id": content_id, "status": "failed", "error": str(exc)}
        self.repository.mark_material_export_synced(
            content_id=content_id,
            central_reference_item_id=response["id"],
        )
        return {
            "content_id": content_id,
            "status": "synced",
            "reference_library_item": response,
        }

    async def _promote_content(self, content_id: int) -> str:
        detail = self.repository.get_content_detail(content_id)
        if not detail:
            raise ValueError("local content not found")
        response = await self.central_session.promote_content(
            candidate=self._build_promote_candidate(detail),
            detail=self._build_promote_detail(detail),
        )
        central_content_id = str(response["content_id"])
        self.repository.set_content_central_id(
            content_id=content_id,
            central_content_id=central_content_id,
        )
        return central_content_id

    @staticmethod
    def _build_promote_candidate(detail: dict[str, Any]) -> dict[str, Any]:
        content_type = str(detail.get("content_type") or "unknown")
        if content_type not in {"image_text", "video", "unknown"}:
            content_type = "unknown"
        return {
            "platform": detail["platform"],
            "platform_content_id": detail["platform_content_id"],
            "canonical_url": detail.get("canonical_url"),
            "content_type": content_type,
            "title_or_summary": detail.get("title"),
            "cover_url": detail.get("cover_url"),
            "author_platform_id": detail.get("author_platform_id"),
            "author_name": detail.get("author_name"),
            "visible_like_count": detail.get("like_count"),
            "source_surface": "manual_import",
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "platform_context": detail.get("platform_context") or {},
            "raw_payload": {"source": "local_first_material"},
        }

    @staticmethod
    def _build_promote_detail(detail: dict[str, Any]) -> dict[str, Any] | None:
        has_detail = bool(
            detail.get("detail_fetched_at")
            or detail.get("body_text")
            or detail.get("image_urls")
            or detail.get("video_url")
        )
        if not has_detail:
            return None
        return {
            "title": detail.get("title"),
            "body_text": detail.get("body_text"),
            "author_platform_id": detail.get("author_platform_id"),
            "author_name": detail.get("author_name"),
            "author_avatar_url": detail.get("author_avatar_url"),
            "cover_url": detail.get("cover_url"),
            "image_urls": detail.get("image_urls") or [],
            "video_url": detail.get("video_url"),
            "like_count": detail.get("like_count"),
            "comment_count": detail.get("comment_count"),
            "collect_count": detail.get("collect_count"),
            "share_count": detail.get("share_count"),
            "publish_time": _as_isoformat(detail.get("published_at")),
            "raw_payload": {"source": "local_first_material"},
        }

    def _matched_keywords(self, content_id: int) -> list[str]:
        detail = self.repository.get_content_detail(content_id) or {}
        return sorted(
            {
                str(item.get("matched_keyword"))
                for item in detail.get("comment_hits") or []
                if item.get("matched_keyword")
            }
        )

    def _session_meta(self, account_id: str | None) -> dict[str, Any]:
        if account_id and account_id in self.config.account_sessions:
            return dict(self.config.account_sessions[account_id])
        if self.config.cdp_url:
            return {"cdp_url": self.config.cdp_url}
        raise RuntimeError("no local browser session configured")

    def _action_done(self, content_id: int, future) -> None:
        self._running_content_ids.discard(content_id)
        try:
            future.result()
        except Exception:
            return


def _as_isoformat(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _normalize_center_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("central server URL must start with http:// or https://")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("central server URL must not contain credentials, query, or fragment")
    return normalized
