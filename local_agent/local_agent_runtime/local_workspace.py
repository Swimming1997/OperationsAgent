from __future__ import annotations

from typing import Any


class LocalWorkspaceServiceMixin:
    """Local-First workspace operations exposed by the loopback bridge."""

    repository: Any
    local_collection: Any
    local_actions: Any
    loop: Any

    def list_contents(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._require_repository().list_contents(
            keyword=_query_text(query, "keyword"),
            platform=_query_text(query, "platform"),
            source_type=_query_text(query, "source_type"),
            processing_status=_query_text(query, "processing_status"),
            limit=_query_int(query.get("limit", [None])[0]) or 50,
            offset=_query_int(query.get("offset", [None])[0]) or 0,
        )

    def get_content_detail(self, content_id: int) -> dict[str, Any] | None:
        return self._require_repository().get_content_detail(content_id)

    def update_content_status(self, content_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        updated = self._require_repository().update_content_processing_status(
            content_ids=[content_id],
            status=str(payload.get("status") or ""),
        )
        if not updated:
            raise ValueError("content not found")
        return self.get_content_detail(content_id) or {"id": content_id}

    def batch_update_content_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        content_ids = payload.get("content_ids") or []
        updated = self._require_repository().update_content_processing_status(
            content_ids=[int(content_id) for content_id in content_ids],
            status=str(payload.get("status") or ""),
        )
        return {"updated": updated, "status": str(payload.get("status") or "")}

    def list_tasks(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _query_int(query.get("limit", [None])[0]) or 20
        return {"items": self._require_repository().list_collect_tasks(limit=limit)}

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        return self._require_repository().get_collect_task(task_id)

    def submit_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.submit_collection_task({"task_type": "search", **payload})

    def submit_search_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.submit_collection_task({"task_type": "search_batch", **payload})

    def submit_search_suggest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.local_collection is None:
            raise RuntimeError("local storage is disabled")
        return self._run_async(
            self.local_collection.fetch_suggestions(
                keyword=str(payload.get("keyword") or ""),
                account_id=str(payload.get("account_id") or "").strip() or None,
            )
        )

    def submit_detail_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.local_actions is None:
            raise RuntimeError("local storage is disabled")
        return self.local_actions.submit_detail_batch(loop=self.loop, payload=payload)

    def search_comments(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._require_repository().search_comments(
            keyword=_query_text(query, "keyword"),
            platform=_query_text(query, "platform"),
            limit=_query_int(query.get("limit", [None])[0]) or 50,
            offset=_query_int(query.get("offset", [None])[0]) or 0,
        )

    def submit_collection_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.local_collection is None:
            raise RuntimeError("local storage is disabled")
        return self.local_collection.submit(loop=self.loop, payload=payload)

    def run_collection_task(self, task_id: int) -> dict[str, Any]:
        if self.local_collection is None:
            raise RuntimeError("local storage is disabled")
        started = self.local_collection.run_task(loop=self.loop, task_id=task_id)
        return {"task_id": task_id, "started": started}

    def update_task_action(self, task_id: int, action: str) -> dict[str, Any]:
        repository = self._require_repository()
        if action == "pause":
            if self.local_collection is None:
                raise RuntimeError("local storage is disabled")
            paused = self.local_collection.pause_task(task_id=task_id)
            return {"task_id": task_id, "paused": paused, **(repository.get_collect_task(task_id) or {})}
        if action == "cancel":
            if self.local_collection is None:
                raise RuntimeError("local storage is disabled")
            cancelled = self.local_collection.cancel_task(task_id=task_id)
            return {"task_id": task_id, "cancelled": cancelled, **(repository.get_collect_task(task_id) or {})}
        if action == "resume":
            if not repository.resume_collect_task(task_id):
                raise ValueError("task not found")
            started = self.local_collection.run_task(loop=self.loop, task_id=task_id)
            return {"task_id": task_id, "started": started, **(repository.get_collect_task(task_id) or {})}
        operations = {
            "viewed": repository.mark_collect_task_viewed,
        }
        operation = operations.get(action)
        if operation is None:
            raise ValueError(f"unsupported task action: {action}")
        if not operation(task_id):
            raise ValueError("task not found")
        return repository.get_collect_task(task_id) or {"task_id": task_id}

    def submit_acquisition_check(self, content_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.local_actions is None:
            raise RuntimeError("local storage is disabled")
        return self.local_actions.submit_acquisition_check(
            loop=self.loop,
            content_id=content_id,
            payload=payload,
        )

    def submit_detail_fetch(self, content_id: int) -> dict[str, Any]:
        if self.local_actions is None:
            raise RuntimeError("local storage is disabled")
        return self.local_actions.submit_detail_fetch(
            loop=self.loop,
            content_id=content_id,
        )

    def central_session_status(self) -> dict[str, Any]:
        return self._require_actions().central_status()

    def central_session_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_async(self._require_actions().login_central(payload))

    def central_session_logout(self) -> dict[str, Any]:
        return self._require_actions().logout_central()

    def add_to_material_library(self, content_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_async(
            self._require_actions().add_to_material_library(
                content_id=content_id,
                payload=payload,
            )
        )

    def retry_material_library(self) -> dict[str, Any]:
        return self._run_async(self._require_actions().retry_pending_materials())

    def _require_repository(self):
        if self.repository is None:
            raise RuntimeError("local storage is disabled")
        return self.repository

    def _require_actions(self):
        if self.local_actions is None:
            raise RuntimeError("local storage is disabled")
        return self.local_actions


def _query_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _query_text(query: dict[str, list[str]], key: str) -> str | None:
    value = query.get(key, [None])[0]
    if value is None:
        return None
    value = str(value).strip()
    return value or None
