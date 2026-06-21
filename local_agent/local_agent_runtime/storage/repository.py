from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from local_agent_runtime.contracts import (
    CommentIngestionRequest,
    CreatorMonitorIngestionRequest,
    DetailIngestionRequest,
    FeedCandidateIngestionRequest,
)
from local_agent_runtime.storage.schema import initialize_schema
from local_agent_runtime.storage.workspace_repository import LocalWorkspaceRepositoryMixin
from local_agent_runtime.connectors.xhs.normalizer import extract_xhs_card_image_urls


DEFAULT_ACQUISITION_KEYWORDS = ("求推荐", "怎么买", "多少钱", "链接", "购买", "求链接")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: datetime | None, *, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class LocalIntelligenceRepository(LocalWorkspaceRepositoryMixin):
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            initialize_schema(connection)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def upsert_feed_candidates(self, request: FeedCandidateIngestionRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self.connection() as connection:
            for candidate in request.candidates:
                discovered_at = _iso(candidate.discovered_at, fallback=_now_iso()) or _now_iso()
                raw = candidate.raw_payload or {}
                api_raw = raw.get("api_raw") if isinstance(raw.get("api_raw"), dict) else raw
                image_urls = [
                    str(url)
                    for url in (raw.get("image_urls") or extract_xhs_card_image_urls(api_raw))
                    if str(url).strip()
                ]
                existing_content = connection.execute(
                    "SELECT id FROM content WHERE platform = ? AND platform_content_id = ?",
                    (str(candidate.platform), candidate.platform_content_id),
                ).fetchone()
                creator_id = self._upsert_creator(
                    connection,
                    platform=str(candidate.platform),
                    platform_user_id=candidate.author_platform_id,
                    nickname=candidate.author_name,
                    avatar_url=raw.get("author_avatar_url") or raw.get("avatar_url"),
                    raw=(
                        raw.get("creator_profile")
                        if isinstance(raw.get("creator_profile"), dict)
                        else (raw.get("author") if isinstance(raw.get("author"), dict) else {})
                    ),
                    seen_at=discovered_at,
                )
                connection.execute(
                    """
                    INSERT INTO content(
                        platform, platform_content_id, creator_id, canonical_url, content_type,
                        title, cover_url, like_count, raw_json, platform_context_json,
                        image_urls_json, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, platform_content_id) DO UPDATE SET
                        creator_id = COALESCE(excluded.creator_id, content.creator_id),
                        canonical_url = COALESCE(excluded.canonical_url, content.canonical_url),
                        content_type = CASE WHEN excluded.content_type != 'unknown'
                            THEN excluded.content_type ELSE content.content_type END,
                        title = COALESCE(excluded.title, content.title),
                        cover_url = COALESCE(excluded.cover_url, content.cover_url),
                        like_count = COALESCE(excluded.like_count, content.like_count),
                        image_urls_json = CASE
                            WHEN excluded.image_urls_json != '[]' THEN excluded.image_urls_json
                            ELSE content.image_urls_json
                        END,
                        raw_json = excluded.raw_json,
                        platform_context_json = excluded.platform_context_json,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        str(candidate.platform),
                        candidate.platform_content_id,
                        creator_id,
                        candidate.canonical_url,
                        str(candidate.content_type),
                        candidate.title_or_summary,
                        candidate.cover_url,
                        candidate.visible_like_count,
                        _json(raw),
                        _json(candidate.platform_context or {}),
                        _json(image_urls),
                        discovered_at,
                        discovered_at,
                    ),
                )
                content_row = connection.execute(
                    "SELECT id, first_seen_at FROM content WHERE platform = ? AND platform_content_id = ?",
                    (str(candidate.platform), candidate.platform_content_id),
                ).fetchone()
                source_type, source_ref = self._source_identity(str(candidate.source_surface), raw)
                connection.execute(
                    """
                    INSERT INTO content_source(
                        content_id, source_type, source_ref, job_id, account_id,
                        first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(content_id, source_type, source_ref) DO UPDATE SET
                        job_id = excluded.job_id,
                        account_id = excluded.account_id,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        content_row["id"],
                        source_type,
                        source_ref,
                        request.job_id,
                        request.account_id,
                        discovered_at,
                        discovered_at,
                    ),
                )
                rows.append(
                    {
                        "local_content_id": content_row["id"],
                        "platform": str(candidate.platform),
                        "platform_content_id": candidate.platform_content_id,
                        "is_new_content": existing_content is None,
                    }
                )
            connection.commit()
        return rows

    def apply_central_content_mappings(self, results: list[dict[str, Any]]) -> None:
        with self.connection() as connection:
            for item in results:
                central_content_id = item.get("content_id")
                platform_content_id = item.get("platform_content_id")
                if not central_content_id or not platform_content_id:
                    continue
                platform = item.get("platform")
                if platform:
                    connection.execute(
                        """
                        UPDATE content SET central_content_id = ?
                        WHERE platform = ? AND platform_content_id = ?
                        """,
                        (central_content_id, platform, platform_content_id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE content SET central_content_id = ?
                        WHERE platform_content_id = ?
                        """,
                        (central_content_id, platform_content_id),
                    )
            connection.commit()

    def upsert_detail(self, request: DetailIngestionRequest) -> int | None:
        snapshot = request.snapshot
        raw = snapshot.raw_payload or {}
        now = _now_iso()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT id, platform FROM content WHERE central_content_id = ?",
                (request.content_id,),
            ).fetchone()
            if row is None:
                platform_content_id = (
                    raw.get("platform_content_id")
                    or raw.get("note_id")
                    or raw.get("id")
                    or raw.get("aweme_id")
                )
                if platform_content_id:
                    row = connection.execute(
                        "SELECT id, platform FROM content WHERE platform_content_id = ?",
                        (str(platform_content_id),),
                    ).fetchone()
            if row is None:
                self.enqueue_outbox(
                    operation="local_detail_unmatched",
                    dedupe_key=request.job_id,
                    payload=request.model_dump(mode="json"),
                    connection=connection,
                )
                connection.commit()
                return None
            creator_id = self._upsert_creator(
                connection,
                platform=row["platform"],
                platform_user_id=snapshot.author_platform_id,
                nickname=snapshot.author_name,
                avatar_url=snapshot.author_avatar_url,
                raw=raw.get("author") if isinstance(raw.get("author"), dict) else {},
                seen_at=now,
            )
            connection.execute(
                """
                UPDATE content SET
                    central_content_id = COALESCE(central_content_id, ?),
                    creator_id = COALESCE(?, creator_id),
                    title = COALESCE(?, title),
                    body_text = COALESCE(?, body_text),
                    cover_url = COALESCE(?, cover_url),
                    image_urls_json = ?,
                    video_url = COALESCE(?, video_url),
                    like_count = COALESCE(?, like_count),
                    comment_count = COALESCE(?, comment_count),
                    collect_count = COALESCE(?, collect_count),
                    share_count = COALESCE(?, share_count),
                    published_at = COALESCE(?, published_at),
                    detail_fetched_at = ?,
                    raw_json = ?
                WHERE id = ?
                """,
                (
                    request.content_id,
                    creator_id,
                    snapshot.title,
                    snapshot.body_text,
                    snapshot.cover_url,
                    _json(snapshot.image_urls),
                    snapshot.video_url,
                    snapshot.like_count,
                    snapshot.comment_count,
                    snapshot.collect_count,
                    snapshot.share_count,
                    _iso(snapshot.publish_time),
                    now,
                    _json(raw),
                    row["id"],
                ),
            )
            connection.commit()
            return int(row["id"])

    def upsert_comments(self, request: CommentIngestionRequest) -> dict[str, int]:
        with self.connection() as connection:
            content = connection.execute(
                "SELECT id FROM content WHERE central_content_id = ?",
                (request.content_id,),
            ).fetchone()
            if content is None:
                self.enqueue_outbox(
                    operation="local_comments_unmatched",
                    dedupe_key=request.job_id,
                    payload=request.model_dump(mode="json"),
                    connection=connection,
                )
                connection.commit()
                return {"inserted": 0, "updated": 0}
        return self.upsert_local_comment_hits(
            content_id=int(content["id"]),
            comments=request.comments,
        )

    def upsert_local_comment_hits(
        self,
        *,
        content_id: int,
        comments: list[Any],
        keywords: list[str] | tuple[str, ...] = DEFAULT_ACQUISITION_KEYWORDS,
        replace: bool = False,
    ) -> dict[str, int]:
        now = _now_iso()
        inserted = 0
        updated = 0
        normalized_keywords = tuple(
            keyword.strip() for keyword in keywords if str(keyword).strip()
        )
        with self.connection() as connection:
            content = connection.execute(
                "SELECT id FROM content WHERE id = ?",
                (content_id,),
            ).fetchone()
            if content is None:
                raise ValueError("local content not found")
            if replace:
                connection.execute(
                    "DELETE FROM comment_hit WHERE content_id = ?",
                    (content_id,),
                )
            for comment in comments:
                matched_keywords = [
                    keyword for keyword in normalized_keywords if keyword in comment.body_text
                ]
                for keyword in matched_keywords:
                    existing = connection.execute(
                        """
                        SELECT id FROM comment_hit
                        WHERE content_id = ? AND platform_comment_id = ? AND matched_keyword = ?
                        """,
                        (content["id"], comment.platform_comment_id, keyword),
                    ).fetchone()
                    connection.execute(
                        """
                        INSERT INTO comment_hit(
                            content_id, platform_comment_id, parent_platform_comment_id,
                            comment_text, comment_author, like_count, matched_keyword,
                            published_at, fetched_at, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(content_id, platform_comment_id, matched_keyword) DO UPDATE SET
                            parent_platform_comment_id = excluded.parent_platform_comment_id,
                            comment_text = excluded.comment_text,
                            comment_author = excluded.comment_author,
                            like_count = excluded.like_count,
                            published_at = excluded.published_at,
                            fetched_at = excluded.fetched_at,
                            raw_json = excluded.raw_json
                        """,
                        (
                            content["id"],
                            comment.platform_comment_id,
                            comment.parent_platform_comment_id,
                            comment.body_text,
                            comment.author_name,
                            comment.like_count,
                            keyword,
                            _iso(comment.created_time),
                            now,
                            _json(comment.raw_payload or {}),
                        ),
                    )
                    if existing is None:
                        inserted += 1
                    else:
                        updated += 1
            hit_count = connection.execute(
                "SELECT COUNT(DISTINCT platform_comment_id) FROM comment_hit WHERE content_id = ?",
                (content["id"],),
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE content
                SET acquisition_hit_count = ?, acquisition_checked_at = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (hit_count, now, now, content["id"]),
            )
            connection.commit()
        return {"inserted": inserted, "updated": updated}

    def upsert_comments_full(
        self,
        *,
        content_id: int,
        comments: list[Any],
        keywords: list[str] | tuple[str, ...] = DEFAULT_ACQUISITION_KEYWORDS,
        replace: bool = True,
    ) -> dict[str, int]:
        """Store every fetched comment (not just acquisition hits) so they are searchable.

        Full comments land in the ``comment`` table; acquisition hits are still
        refreshed via :meth:`upsert_local_comment_hits` so the existing
        获客信号 surface keeps working.
        """
        now = _now_iso()
        stored = 0
        with self.connection() as connection:
            content = connection.execute(
                "SELECT id FROM content WHERE id = ?",
                (content_id,),
            ).fetchone()
            if content is None:
                raise ValueError("local content not found")
            if replace:
                connection.execute(
                    "DELETE FROM comment WHERE content_id = ?",
                    (content_id,),
                )
            for comment in comments:
                comment_id = getattr(comment, "platform_comment_id", None)
                if not comment_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO comment(
                        content_id, platform_comment_id, parent_platform_comment_id,
                        comment_text, comment_author, author_platform_id, like_count,
                        published_at, fetched_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(content_id, platform_comment_id) DO UPDATE SET
                        parent_platform_comment_id = excluded.parent_platform_comment_id,
                        comment_text = excluded.comment_text,
                        comment_author = excluded.comment_author,
                        author_platform_id = excluded.author_platform_id,
                        like_count = excluded.like_count,
                        published_at = excluded.published_at,
                        fetched_at = excluded.fetched_at,
                        raw_json = excluded.raw_json
                    """,
                    (
                        content_id,
                        comment_id,
                        getattr(comment, "parent_platform_comment_id", None),
                        getattr(comment, "body_text", ""),
                        getattr(comment, "author_name", None),
                        getattr(comment, "author_platform_id", None),
                        getattr(comment, "like_count", None),
                        _iso(getattr(comment, "created_time", None)),
                        now,
                        _json(getattr(comment, "raw_payload", None) or {}),
                    ),
                )
                stored += 1
            total = connection.execute(
                "SELECT COUNT(*) FROM comment WHERE content_id = ?",
                (content_id,),
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE content
                SET comment_count = COALESCE(?, comment_count),
                    comments_fetched_at = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (total, now, now, content_id),
            )
            connection.commit()
        hits = self.upsert_local_comment_hits(
            content_id=content_id,
            comments=comments,
            keywords=keywords,
            replace=True,
        )
        return {"stored": stored, "total": int(total), **hits}

    def search_comments(
        self,
        *,
        keyword: str | None = None,
        platform: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []
        if keyword:
            conditions.append("LOWER(cm.comment_text) LIKE ?")
            params.append(f"%{keyword.lower()}%")
        if platform:
            conditions.append("c.platform = ?")
            params.append(platform)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connection() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM comment cm
                JOIN content c ON c.id = cm.content_id
                {where}
                """,
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    cm.id, cm.content_id, cm.comment_text, cm.comment_author,
                    cm.like_count, cm.published_at, cm.fetched_at,
                    c.platform, c.platform_content_id, c.title AS content_title,
                    c.canonical_url, cr.nickname AS content_author
                FROM comment cm
                JOIN content c ON c.id = cm.content_id
                LEFT JOIN creator cr ON cr.id = c.creator_id
                {where}
                ORDER BY cm.like_count DESC, cm.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, max(1, min(limit, 100)), max(0, offset)],
            ).fetchall()
            return {
                "items": [dict(row) for row in rows],
                "total": int(total),
                "limit": limit,
                "offset": offset,
            }

    def list_content_comments(self, content_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT platform_comment_id, comment_text, comment_author,
                    like_count, published_at, fetched_at
                FROM comment WHERE content_id = ?
                ORDER BY like_count DESC, id DESC
                LIMIT ?
                """,
                (content_id, max(1, min(limit, 500))),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_pending_detail_contents(
        self,
        *,
        platform: str | None = None,
        content_ids: list[int] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Notes that still need detail (body) or comments fetched.

        Used by the multi-account detail dispatcher to decide what to pull.
        """
        conditions = ["c.processing_status != 'discarded'"]
        params: list[Any] = []
        if content_ids:
            normalized = sorted({int(item) for item in content_ids if int(item) > 0})
            if not normalized:
                return []
            placeholders = ",".join("?" for _ in normalized)
            conditions.append(f"c.id IN ({placeholders})")
            params.extend(normalized)
        else:
            conditions.append("(c.detail_fetched_at IS NULL OR c.comments_fetched_at IS NULL)")
        if platform:
            conditions.append("c.platform = ?")
            params.append(platform)
        where = " AND ".join(conditions)
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.id, c.platform, c.platform_content_id, c.canonical_url,
                    c.platform_context_json, c.detail_fetched_at, c.comments_fetched_at,
                    cr.nickname AS author_name
                FROM content c
                LEFT JOIN creator cr ON cr.id = c.creator_id
                WHERE {where}
                ORDER BY c.first_seen_at DESC, c.id DESC
                LIMIT ?
                """,
                [*params, max(1, min(limit, 500))],
            ).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["platform_context"] = json.loads(item.pop("platform_context_json") or "{}")
                results.append(item)
            return results

    def upsert_creator_monitor(self, request: CreatorMonitorIngestionRequest) -> list[dict[str, Any]]:
        feed_request = FeedCandidateIngestionRequest(
            job_id=request.job_id,
            account_id=request.account_id,
            candidates=request.items,
        )
        return self.upsert_feed_candidates(feed_request)

    def upsert_search_suggestions(self, payload: dict[str, Any], *, default_platform: str) -> int:
        platform = str(payload.get("platform") or default_platform)
        core_keyword = str(payload.get("core_keyword") or "").strip()
        now = _now_iso()
        count = 0
        with self.connection() as connection:
            for index, item in enumerate(payload.get("items") or [], start=1):
                if isinstance(item, str):
                    suggested_keyword = item
                    rank = index
                    raw = {}
                else:
                    suggested_keyword = str(
                        item.get("suggested_keyword")
                        or item.get("keyword")
                        or item.get("content")
                        or ""
                    ).strip()
                    rank = item.get("suggestion_rank") or item.get("rank") or index
                    raw = item
                if not suggested_keyword:
                    continue
                connection.execute(
                    """
                    INSERT INTO search_suggestion(
                        platform, core_keyword, suggested_keyword, rank, fetched_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, core_keyword, suggested_keyword) DO UPDATE SET
                        rank = excluded.rank,
                        fetched_at = excluded.fetched_at,
                        raw_json = excluded.raw_json
                    """,
                    (platform, core_keyword, suggested_keyword, rank, now, _json(raw)),
                )
                count += 1
            connection.commit()
        return count

    def enqueue_outbox(
        self,
        *,
        operation: str,
        dedupe_key: str,
        payload: dict[str, Any],
        error: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        owns_connection = connection is None
        context = self.connection() if owns_connection else None
        target = context.__enter__() if context else connection
        now = _now_iso()
        try:
            target.execute(
                """
                INSERT INTO ingestion_outbox(
                    operation, dedupe_key, payload_json, status, attempts,
                    last_error, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', 1, ?, ?, ?)
                ON CONFLICT(operation, dedupe_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    status = 'pending',
                    attempts = ingestion_outbox.attempts + 1,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (operation, dedupe_key, _json(payload), error, now, now),
            )
            if owns_connection:
                target.commit()
        finally:
            if context:
                context.__exit__(None, None, None)

    def start_collect_run(self, *, central_job_id: str, job_type: str) -> None:
        now = _now_iso()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO collect_run(
                    central_job_id, job_type, status, started_at, attempts
                ) VALUES (?, ?, 'running', ?, 1)
                ON CONFLICT(central_job_id) DO UPDATE SET
                    job_type = excluded.job_type,
                    status = 'running',
                    started_at = excluded.started_at,
                    finished_at = NULL,
                    attempts = collect_run.attempts + 1,
                    error_summary_json = '{}'
                """,
                (central_job_id, job_type, now),
            )
            connection.commit()

    def list_pending_outbox(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM ingestion_outbox
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_outbox_sent(self, outbox_id: int) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_outbox
                SET status = 'sent', last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (_now_iso(), outbox_id),
            )
            connection.commit()

    def mark_outbox_failed(self, outbox_id: int, error: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_outbox
                SET attempts = attempts + 1, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error, _now_iso(), outbox_id),
            )
            connection.commit()

    def update_collect_run_progress(
        self,
        *,
        central_job_id: str,
        item_count: int,
        error_summary: dict[str, Any] | None = None,
    ) -> None:
        """Write incremental progress for a running run so the UI can poll it.

        Real-time feedback principle (see 技术方案 §8.1): long tasks must persist
        progress per item instead of only at the end.
        """
        with self.connection() as connection:
            if error_summary is None:
                connection.execute(
                    "UPDATE collect_run SET item_count = ? WHERE central_job_id = ?",
                    (int(item_count), central_job_id),
                )
            else:
                connection.execute(
                    "UPDATE collect_run SET item_count = ?, error_summary_json = ? WHERE central_job_id = ?",
                    (int(item_count), _json(error_summary), central_job_id),
                )
            connection.commit()

    def finish_collect_run(
        self,
        *,
        central_job_id: str,
        status: str,
        item_count: int = 0,
        error_summary: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE collect_run
                SET status = ?, finished_at = ?, item_count = ?, error_summary_json = ?
                WHERE central_job_id = ?
                """,
                (status, _now_iso(), item_count, _json(error_summary or {}), central_job_id),
            )
            connection.commit()

    def table_count(self, table: str) -> int:
        allowed = {
            "creator",
            "content",
            "content_source",
            "comment_hit",
            "comment",
            "search_suggestion",
            "collect_task",
            "collect_run",
            "ingestion_outbox",
            "material_export",
            "local_setting",
        }
        if table not in allowed:
            raise ValueError(f"unsupported table: {table}")
        with self.connection() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT value FROM local_setting WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO local_setting(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _now_iso()),
            )
            connection.commit()

    def get_content(self, *, platform: str, platform_content_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM content WHERE platform = ? AND platform_content_id = ?",
                (platform, platform_content_id),
            ).fetchone()
            return dict(row) if row else None

    def get_collect_run(self, central_job_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM collect_run WHERE central_job_id = ?",
                (central_job_id,),
            ).fetchone()
            return dict(row) if row else None

    def _upsert_creator(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        platform_user_id: str | None,
        nickname: str | None,
        avatar_url: str | None,
        raw: dict[str, Any],
        seen_at: str,
    ) -> int | None:
        if not platform_user_id:
            return None
        connection.execute(
            """
            INSERT INTO creator(
                platform, platform_user_id, nickname, avatar_url, fans_count,
                total_liked_collected, works_count, verify_type, signature,
                ip_location, raw_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, platform_user_id) DO UPDATE SET
                nickname = COALESCE(excluded.nickname, creator.nickname),
                avatar_url = COALESCE(excluded.avatar_url, creator.avatar_url),
                fans_count = COALESCE(excluded.fans_count, creator.fans_count),
                total_liked_collected = COALESCE(excluded.total_liked_collected, creator.total_liked_collected),
                works_count = COALESCE(excluded.works_count, creator.works_count),
                verify_type = COALESCE(excluded.verify_type, creator.verify_type),
                signature = COALESCE(excluded.signature, creator.signature),
                ip_location = COALESCE(excluded.ip_location, creator.ip_location),
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                platform,
                platform_user_id,
                raw.get("nickname") or nickname,
                raw.get("avatar_url") or avatar_url,
                raw.get("fans_count"),
                raw.get("total_liked_collected"),
                raw.get("works_count"),
                raw.get("verify_type"),
                raw.get("signature"),
                raw.get("ip_location"),
                _json(raw.get("raw") or raw),
                seen_at,
                seen_at,
            ),
        )
        row = connection.execute(
            "SELECT id FROM creator WHERE platform = ? AND platform_user_id = ?",
            (platform, platform_user_id),
        ).fetchone()
        return int(row["id"])

    @staticmethod
    def _source_identity(source_surface: str, raw: dict[str, Any]) -> tuple[str, str]:
        if source_surface in {"search", "xhs_search"}:
            return "search", str(raw.get("search_keyword") or raw.get("keyword") or "")
        if source_surface in {"creator", "creator_monitor", "account_posted_notes"}:
            return "creator", str(
                raw.get("creator_monitor_ref")
                or raw.get("creator_platform_id")
                or raw.get("author_platform_id")
                or raw.get("user_id")
                or ""
            )
        return "recommend", source_surface
