from __future__ import annotations

import json
from typing import Any

from local_agent_runtime.contracts import (
    CommentIngestionRequest,
    CreatorMonitorIngestionRequest,
    DetailIngestionRequest,
    FeedCandidateIngestionRequest,
)
from local_agent_runtime.storage.repository import LocalIntelligenceRepository


class LocalFirstIngestionGateway:
    """Persist normalized intelligence locally before forwarding to Central."""

    def __init__(self, *, remote: Any, repository: LocalIntelligenceRepository):
        self.remote = remote
        self.repository = repository

    def __getattr__(self, name: str) -> Any:
        return getattr(self.remote, name)

    async def flush_pending_outbox(self, *, limit: int = 20) -> dict[str, int]:
        sent = 0
        failed = 0
        for row in self.repository.list_pending_outbox(limit=limit):
            try:
                payload = json.loads(row["payload_json"])
                response = await self._replay(row["operation"], payload)
                if row["operation"] == "feed_candidates":
                    request = FeedCandidateIngestionRequest.model_validate(payload)
                    self.repository.apply_central_content_mappings(
                        self._mapped_results((response or {}).get("results") or [], request.candidates)
                    )
                self.repository.mark_outbox_sent(row["id"])
                sent += 1
            except Exception as exc:
                self.repository.mark_outbox_failed(row["id"], str(exc))
                failed += 1
        return {"sent": sent, "failed": failed}

    async def _replay(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "feed_candidates":
            return await self.remote.ingest_feed_candidates(FeedCandidateIngestionRequest.model_validate(payload))
        if operation == "content_detail":
            return await self.remote.ingest_detail(DetailIngestionRequest.model_validate(payload))
        if operation == "comments":
            return await self.remote.ingest_comments(CommentIngestionRequest.model_validate(payload))
        if operation == "creator_monitor_items":
            return await self.remote.ingest_creator_monitor_items(CreatorMonitorIngestionRequest.model_validate(payload))
        if operation == "xhs_search_suggestions":
            return await self.remote.ingest_xhs_search_suggestions(payload)
        if operation == "search_suggestions":
            return await self.remote.ingest_search_suggestions(payload)
        raise ValueError(f"unsupported outbox operation: {operation}")

    async def ingest_feed_candidates(self, payload: FeedCandidateIngestionRequest) -> dict[str, Any]:
        local_results = self.repository.upsert_feed_candidates(payload)
        try:
            response = await self.remote.ingest_feed_candidates(payload)
        except Exception as exc:
            self.repository.enqueue_outbox(
                operation="feed_candidates",
                dedupe_key=payload.job_id,
                payload=payload.model_dump(mode="json"),
                error=str(exc),
            )
            raise
        self.repository.apply_central_content_mappings(
            self._mapped_results(response.get("results") or [], payload.candidates)
        )
        return response or {"results": local_results}

    async def ingest_detail(self, payload: DetailIngestionRequest) -> dict[str, Any]:
        self.repository.upsert_detail(payload)
        try:
            return await self.remote.ingest_detail(payload)
        except Exception as exc:
            self.repository.enqueue_outbox(
                operation="content_detail",
                dedupe_key=payload.job_id,
                payload=payload.model_dump(mode="json"),
                error=str(exc),
            )
            raise

    async def ingest_comments(self, payload: CommentIngestionRequest) -> dict[str, Any]:
        local_result = self.repository.upsert_comments(payload)
        try:
            return await self.remote.ingest_comments(payload)
        except Exception as exc:
            self.repository.enqueue_outbox(
                operation="comments",
                dedupe_key=payload.job_id,
                payload=payload.model_dump(mode="json"),
                error=str(exc),
            )
            raise

    async def ingest_creator_monitor_items(self, payload: CreatorMonitorIngestionRequest) -> dict[str, Any]:
        local_results = self.repository.upsert_creator_monitor(payload)
        try:
            response = await self.remote.ingest_creator_monitor_items(payload)
        except Exception as exc:
            self.repository.enqueue_outbox(
                operation="creator_monitor_items",
                dedupe_key=payload.job_id,
                payload=payload.model_dump(mode="json"),
                error=str(exc),
            )
            raise
        self.repository.apply_central_content_mappings(
            self._mapped_results(response.get("results") or [], payload.items)
        )
        return response

    async def ingest_xhs_search_suggestions(self, payload: dict[str, Any]) -> dict[str, Any]:
        local_count = self.repository.upsert_search_suggestions(payload, default_platform="xhs")
        try:
            return await self.remote.ingest_xhs_search_suggestions(payload)
        except Exception as exc:
            self.repository.enqueue_outbox(
                operation="xhs_search_suggestions",
                dedupe_key=str(payload.get("job_id") or payload.get("core_keyword") or ""),
                payload=payload,
                error=str(exc),
            )
            raise

    async def ingest_search_suggestions(self, payload: dict[str, Any]) -> dict[str, Any]:
        local_count = self.repository.upsert_search_suggestions(
            payload,
            default_platform=str(payload.get("platform") or "xhs"),
        )
        try:
            return await self.remote.ingest_search_suggestions(payload)
        except Exception as exc:
            self.repository.enqueue_outbox(
                operation="search_suggestions",
                dedupe_key=str(payload.get("job_id") or payload.get("core_keyword") or ""),
                payload=payload,
                error=str(exc),
            )
            raise

    @staticmethod
    def _mapped_results(results: list[dict[str, Any]], candidates: list[Any]) -> list[dict[str, Any]]:
        platforms = {
            candidate.platform_content_id: str(candidate.platform)
            for candidate in candidates
        }
        return [
            {
                **item,
                "platform": item.get("platform") or platforms.get(item.get("platform_content_id")),
            }
            for item in results
        ]
