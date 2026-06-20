from __future__ import annotations

import asyncio
import uuid
from typing import Any

from local_agent_runtime.connectors.xhs.creator import XhsCreatorConnector
from local_agent_runtime.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe
from local_agent_runtime.contracts import FeedCandidateIngestionRequest, FeedCandidateInput
from local_agent_runtime.enums import Platform, SessionStatus, SourceSurface
from local_agent_runtime.runtime import AgentRuntimeConfig
from local_agent_runtime.sessions.registry import default_session_registry
from local_agent_runtime.storage.repository import LocalIntelligenceRepository


class LocalCollectionService:
    SUPPORTED_TASK_TYPES = {"search", "creator_monitor", "recommend"}

    def __init__(self, *, config: AgentRuntimeConfig, repository: LocalIntelligenceRepository):
        self.config = config
        self.repository = repository
        self._running_task_ids: set[int] = set()
        self._running_futures: dict[int, Any] = {}

    def submit(self, *, loop: asyncio.AbstractEventLoop, payload: dict[str, Any]) -> dict[str, Any]:
        task_type = str(payload.get("task_type") or "search").strip()
        if task_type not in self.SUPPORTED_TASK_TYPES:
            raise ValueError(f"unsupported task_type: {task_type}")
        target = str(payload.get("target") or payload.get("keyword") or "").strip()
        if task_type in {"search", "creator_monitor"} and not target:
            raise ValueError("target is required")
        platform = str(payload.get("platform") or Platform.XHS.value)
        if platform != Platform.XHS.value:
            raise ValueError("local collection currently supports xhs")
        schedule_seconds = payload.get("schedule_seconds")
        if schedule_seconds is not None:
            schedule_seconds = max(60, int(schedule_seconds))
        params = {
            "platform": platform,
            "account_id": str(payload.get("account_id") or "").strip() or None,
            "max_items": max(1, min(int(payload.get("max_items") or 30), 100)),
            "sort": str(payload.get("sort") or "comprehensive"),
            "content_form": str(payload.get("content_form") or "all"),
            "publish_time": str(payload.get("publish_time") or "all"),
            "creator_profile_url": str(payload.get("creator_profile_url") or target).strip(),
            "creator_platform_id": str(payload.get("creator_platform_id") or "").strip() or None,
        }
        task_id = self.repository.create_collect_task(
            task_type=task_type,
            target=target,
            params=params,
            schedule_seconds=schedule_seconds,
        )
        self.run_task(loop=loop, task_id=task_id)
        return {"task_id": task_id, "status": "queued", "task_type": task_type}

    def run_task(self, *, loop: asyncio.AbstractEventLoop, task_id: int) -> bool:
        if task_id in self._running_task_ids:
            return False
        task = self.repository.get_collect_task(task_id)
        if not task:
            raise ValueError("task not found")
        self._running_task_ids.add(task_id)
        future = asyncio.run_coroutine_threadsafe(self._execute(task), loop)
        self._running_futures[task_id] = future
        future.add_done_callback(lambda completed, item_id=task_id: self._task_done(item_id, completed))
        return True

    def pause_task(self, *, task_id: int) -> bool:
        return self._interrupt_task(task_id=task_id, status="paused", reason="任务已暂停")

    def cancel_task(self, *, task_id: int) -> bool:
        return self._interrupt_task(task_id=task_id, status="failed", reason="任务已取消")

    def _interrupt_task(self, *, task_id: int, status: str, reason: str) -> bool:
        if not self.repository.get_collect_task(task_id):
            raise ValueError("task not found")
        future = self._running_futures.get(task_id)
        if not self.repository.interrupt_collect_task(task_id, status=status, reason=reason):
            return False
        if task_id not in self._running_task_ids or future is None:
            return True
        if isinstance(future, asyncio.Task):
            future.get_loop().call_soon_threadsafe(future.cancel)
        else:
            future.cancel()
        return True

    async def run_due_tasks(self) -> int:
        started = 0
        for task in self.repository.list_due_collect_tasks(limit=20):
            task_id = int(task["id"])
            if task_id in self._running_task_ids:
                continue
            self._running_task_ids.add(task_id)
            started += 1
            future = asyncio.create_task(self._execute_with_cleanup(task))
            self._running_futures[task_id] = future
        return started

    async def _execute_with_cleanup(self, task: dict[str, Any]) -> None:
        task_id = int(task["id"])
        try:
            await self._execute(task)
        finally:
            self._running_task_ids.discard(task_id)
            self._running_futures.pop(task_id, None)

    def _task_done(self, task_id: int, future) -> None:
        self._running_task_ids.discard(task_id)
        self._running_futures.pop(task_id, None)
        try:
            future.result()
        except (Exception, asyncio.CancelledError):
            return

    async def _execute(self, task: dict[str, Any]) -> None:
        task_id = int(task["id"])
        task_type = str(task["task_type"])
        params = task.get("params") or {}
        run_id = f"local-{task_type}-{task_id}-{uuid.uuid4().hex[:8]}"
        self.repository.mark_collect_task_running(task_id)
        self.repository.start_local_collect_run(task_id=task_id, run_id=run_id, job_type=task_type)
        session = None
        try:
            session_meta = self._session_meta(params.get("account_id"))
            session = await default_session_registry.create(Platform.XHS.value).acquire(session_meta=session_meta)
            if session.status != SessionStatus.READY:
                raise RuntimeError(session.message or f"session status: {session.status}")
            candidates, report = await self._collect(task_type, task["target"], params, session.page)
            local_results = self.repository.upsert_feed_candidates(
                FeedCandidateIngestionRequest(
                    job_id=run_id,
                    account_id=params.get("account_id"),
                    candidates=candidates,
                )
            )
            new_count = sum(1 for item in local_results if item["is_new_content"])
            self.repository.finish_collect_run(
                central_job_id=run_id,
                status="success",
                item_count=len(candidates),
                error_summary={"report": report, "new_content_count": new_count},
            )
            self.repository.finish_collect_task(task_id, success=True)
        except asyncio.CancelledError:
            return
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

    async def _collect(
        self,
        task_type: str,
        target: str,
        params: dict[str, Any],
        page,
    ) -> tuple[list[FeedCandidateInput], dict[str, Any]]:
        if task_type == "search":
            candidates, report = await XhsSearchProbe(
                keywords=[target],
                max_items=params["max_items"],
                search_sort=params["sort"],
                note_type=params["content_form"],
                publish_time=params["publish_time"],
            ).collect(page)
            return [self._with_source_context(item, source_ref=target) for item in candidates], report
        if task_type == "recommend":
            candidates, report = await XhsHomeFeedProbe(target_count=params["max_items"]).collect(page)
            return candidates, report
        if task_type == "creator_monitor":
            result = await XhsCreatorConnector().fetch_latest(
                page,
                creator_profile_url=params.get("creator_profile_url"),
                creator_platform_id=params.get("creator_platform_id"),
                context={},
                limit=params["max_items"],
            )
            candidates = [
                self._with_creator_context(
                    item.to_candidate(feed_position=index, source_surface=SourceSurface.CREATOR_MONITOR),
                    creator_platform_id=result.creator_platform_id,
                    creator_display_name=result.creator_display_name,
                    creator_monitor_ref=target,
                    creator_profile=result.profile,
                )
                for index, item in enumerate(result.items, start=1)
            ]
            return candidates, {
                "creator_platform_id": result.creator_platform_id,
                "creator_display_name": result.creator_display_name,
                "items_seen": len(candidates),
            }
        raise ValueError(f"unsupported task_type: {task_type}")

    def _session_meta(self, account_id: str | None) -> dict[str, Any]:
        if account_id and account_id in self.config.account_sessions:
            return dict(self.config.account_sessions[account_id])
        if self.config.cdp_url:
            return {"cdp_url": self.config.cdp_url}
        raise RuntimeError("no local browser session configured")

    @staticmethod
    def _with_source_context(candidate: FeedCandidateInput, *, source_ref: str) -> FeedCandidateInput:
        return candidate.model_copy(
            update={"raw_payload": {**(candidate.raw_payload or {}), "search_keyword": source_ref}}
        )

    @staticmethod
    def _with_creator_context(
        candidate: FeedCandidateInput,
        *,
        creator_platform_id: str,
        creator_display_name: str | None,
        creator_monitor_ref: str,
        creator_profile: dict[str, Any],
    ) -> FeedCandidateInput:
        return candidate.model_copy(
            update={
                "author_platform_id": creator_platform_id,
                "author_name": creator_display_name,
                "raw_payload": {
                    **(candidate.raw_payload or {}),
                    "creator_platform_id": creator_platform_id,
                    "creator_monitor_ref": creator_monitor_ref,
                    "creator_profile": creator_profile,
                },
            }
        )


class LocalTaskScheduler:
    def __init__(self, service: LocalCollectionService, *, interval_seconds: float = 2.0):
        self.service = service
        self.interval_seconds = interval_seconds
        self._stopping = False

    async def run_forever(self) -> None:
        while not self._stopping:
            await self.service.run_due_tasks()
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._stopping = True
