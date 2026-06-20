from __future__ import annotations

import asyncio
import uuid
from typing import Any
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
    ):
        self.config = config
        self.repository = repository
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
            error = "content is waiting for central ingestion"
            self.repository.mark_material_export_failed(content_id=content_id, error=error)
            return {"content_id": content_id, "status": "failed", "error": error}
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


def _normalize_center_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("central server URL must start with http:// or https://")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("central server URL must not contain credentials, query, or fragment")
    return normalized
