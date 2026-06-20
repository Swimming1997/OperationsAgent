from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class LocalWorkspaceRepositoryMixin:
        def create_collect_task(
            self,
            *,
            task_type: str,
            target: str,
            params: dict[str, Any],
            schedule_seconds: int | None = None,
        ) -> int:
            now = _now_iso()
            status = "active" if schedule_seconds else "queued"
            with self.connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO collect_task(
                        task_type, target, params_json, schedule_seconds,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (task_type, target, _json(params), schedule_seconds, status, now, now),
                )
                connection.commit()
                return int(cursor.lastrowid)

        def mark_collect_task_running(self, task_id: int) -> None:
            now = _now_iso()
            with self.connection() as connection:
                connection.execute(
                    """
                    UPDATE collect_task
                    SET status = 'running', last_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, task_id),
                )
                connection.commit()

        def finish_collect_task(self, task_id: int, *, success: bool) -> None:
            now = _now_iso()
            with self.connection() as connection:
                task = connection.execute(
                    "SELECT schedule_seconds FROM collect_task WHERE id = ?",
                    (task_id,),
                ).fetchone()
                if not task:
                    return
                status = "active" if task["schedule_seconds"] else ("success" if success else "failed")
                connection.execute(
                    """
                    UPDATE collect_task
                    SET status = ?, last_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, now, task_id),
                )
                connection.commit()

        def pause_collect_task(self, task_id: int) -> bool:
            with self.connection() as connection:
                cursor = connection.execute(
                    "UPDATE collect_task SET status = 'paused', updated_at = ? WHERE id = ?",
                    (_now_iso(), task_id),
                )
                connection.commit()
                return cursor.rowcount > 0

        def interrupt_collect_task(self, task_id: int, *, status: str, reason: str) -> bool:
            if status not in {"paused", "failed"}:
                raise ValueError(f"unsupported interrupted task status: {status}")
            now = _now_iso()
            with self.connection() as connection:
                task = connection.execute(
                    "SELECT id FROM collect_task WHERE id = ?",
                    (task_id,),
                ).fetchone()
                if not task:
                    return False
                latest_run = connection.execute(
                    """
                    SELECT id FROM collect_run
                    WHERE task_id = ? AND status = 'running'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if latest_run:
                    connection.execute(
                        """
                        UPDATE collect_run
                        SET status = ?, finished_at = ?, error_summary_json = ?
                        WHERE id = ?
                        """,
                        (
                            status,
                            now,
                            _json({"message": reason, "interrupted": True}),
                            latest_run["id"],
                        ),
                    )
                connection.execute(
                    """
                    UPDATE collect_task
                    SET status = ?, last_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, now, task_id),
                )
                connection.commit()
                return True

        def resume_collect_task(self, task_id: int) -> bool:
            with self.connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE collect_task
                    SET status = CASE WHEN schedule_seconds IS NULL THEN 'queued' ELSE 'active' END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (_now_iso(), task_id),
                )
                connection.commit()
                return cursor.rowcount > 0

        def mark_collect_task_viewed(self, task_id: int) -> bool:
            now = _now_iso()
            with self.connection() as connection:
                cursor = connection.execute(
                    "UPDATE collect_task SET last_viewed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, task_id),
                )
                connection.commit()
                return cursor.rowcount > 0

        def get_collect_task(self, task_id: int) -> dict[str, Any] | None:
            with self.connection() as connection:
                row = connection.execute(
                    "SELECT * FROM collect_task WHERE id = ?",
                    (task_id,),
                ).fetchone()
                if not row:
                    return None
                result = dict(row)
                result["params"] = json.loads(result.pop("params_json") or "{}")
                run = connection.execute(
                    """
                    SELECT * FROM collect_run
                    WHERE task_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                result["latest_run"] = dict(run) if run else None
                result["new_content_count"] = self._task_new_content_count(connection, result)
                result["next_run_at"] = self._next_run_at(result)
                return result

        def list_collect_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
            with self.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM collect_task
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                results = []
                for row in rows:
                    item = dict(row)
                    item["params"] = json.loads(item.pop("params_json") or "{}")
                    latest_run = connection.execute(
                        """
                        SELECT * FROM collect_run
                        WHERE task_id = ?
                        ORDER BY id DESC LIMIT 1
                        """,
                        (item["id"],),
                    ).fetchone()
                    item["latest_run"] = dict(latest_run) if latest_run else None
                    item["new_content_count"] = self._task_new_content_count(connection, item)
                    item["next_run_at"] = self._next_run_at(item)
                    results.append(item)
                return results

        def list_due_collect_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
            now = datetime.now(timezone.utc)
            with self.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM collect_task
                    WHERE schedule_seconds IS NOT NULL AND status = 'active'
                    ORDER BY COALESCE(last_run_at, created_at) ASC, id ASC
                    """
                ).fetchall()
                results = []
                for row in rows:
                    item = dict(row)
                    last_run_at = self._parse_datetime(item["last_run_at"])
                    created_at = self._parse_datetime(item["created_at"]) or now
                    due_at = (last_run_at or created_at) + timedelta(seconds=int(item["schedule_seconds"]))
                    if due_at > now:
                        continue
                    item["params"] = json.loads(item.pop("params_json") or "{}")
                    results.append(item)
                    if len(results) >= limit:
                        break
                return results

        def start_local_collect_run(self, *, task_id: int, run_id: str, job_type: str) -> None:
            now = _now_iso()
            with self.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO collect_run(
                        task_id, central_job_id, job_type, status, started_at, attempts
                    ) VALUES (?, ?, ?, 'running', ?, 1)
                    """,
                    (task_id, run_id, job_type, now),
                )
                connection.commit()

        def list_contents(
            self,
            *,
            keyword: str | None = None,
            platform: str | None = None,
            source_type: str | None = None,
            processing_status: str | None = None,
            limit: int = 50,
            offset: int = 0,
        ) -> dict[str, Any]:
            conditions: list[str] = []
            params: list[Any] = []
            if keyword:
                conditions.append("(LOWER(c.title) LIKE ? OR LOWER(c.body_text) LIKE ? OR LOWER(cr.nickname) LIKE ?)")
                pattern = f"%{keyword.lower()}%"
                params.extend([pattern, pattern, pattern])
            if platform:
                conditions.append("c.platform = ?")
                params.append(platform)
            if source_type:
                conditions.append("EXISTS (SELECT 1 FROM content_source sx WHERE sx.content_id = c.id AND sx.source_type = ?)")
                params.append(source_type)
            if processing_status:
                if processing_status not in {"pending", "discarded", "material"}:
                    raise ValueError(f"unsupported processing status: {processing_status}")
                conditions.append("c.processing_status = ?")
                params.append(processing_status)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            with self.connection() as connection:
                total = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM content c
                    LEFT JOIN creator cr ON cr.id = c.creator_id
                    {where}
                    """,
                    params,
                ).fetchone()[0]
                rows = connection.execute(
                    f"""
                    SELECT
                        c.id, c.platform, c.platform_content_id, c.canonical_url,
                        c.content_type, c.title, c.cover_url, c.like_count,
                        c.comment_count, c.collect_count, c.share_count,
                        c.published_at, c.last_seen_at, c.acquisition_hit_count,
                        c.processing_status,
                        cr.nickname AS author_name,
                        GROUP_CONCAT(DISTINCT cs.source_type) AS source_types,
                        me.status AS material_status
                    FROM content c
                    LEFT JOIN creator cr ON cr.id = c.creator_id
                    LEFT JOIN content_source cs ON cs.content_id = c.id
                    LEFT JOIN material_export me ON me.content_id = c.id
                    {where}
                    GROUP BY c.id
                    -- 列表按首次采集顺序稳定展示。正文补抓、评论检查和指标刷新
                    -- 都不应把用户正在查看的内容突然移动到列表顶部。
                    ORDER BY c.first_seen_at DESC, c.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    [*params, max(1, min(limit, 100)), max(0, offset)],
                ).fetchall()
                items = []
                for row in rows:
                    item = dict(row)
                    item["source_types"] = (item["source_types"] or "").split(",") if item["source_types"] else []
                    items.append(item)
                return {"items": items, "total": int(total), "limit": limit, "offset": offset}

        def update_content_processing_status(
            self,
            *,
            content_ids: list[int],
            status: str,
        ) -> int:
            if status not in {"pending", "discarded", "material"}:
                raise ValueError(f"unsupported processing status: {status}")
            normalized_ids = sorted({int(content_id) for content_id in content_ids if int(content_id) > 0})
            if not normalized_ids:
                raise ValueError("content_ids are required")
            placeholders = ",".join("?" for _ in normalized_ids)
            with self.connection() as connection:
                cursor = connection.execute(
                    f"UPDATE content SET processing_status = ? WHERE id IN ({placeholders})",
                    [status, *normalized_ids],
                )
                connection.commit()
                return int(cursor.rowcount)

        def get_content_detail(self, content_id: int) -> dict[str, Any] | None:
            with self.connection() as connection:
                row = connection.execute(
                    """
                    SELECT c.*, cr.platform_user_id AS author_platform_id,
                        cr.nickname AS author_name, cr.avatar_url AS author_avatar_url,
                        cr.fans_count AS author_fans_count,
                        cr.total_liked_collected AS author_total_liked_collected,
                        cr.works_count AS author_works_count,
                        cr.verify_type AS author_verify_type,
                        cr.signature AS author_signature,
                        cr.ip_location AS author_ip_location
                    FROM content c
                    LEFT JOIN creator cr ON cr.id = c.creator_id
                    WHERE c.id = ?
                    """,
                    (content_id,),
                ).fetchone()
                if not row:
                    return None
                result = dict(row)
                for key in ("topics_json", "platform_tags_json", "image_urls_json", "raw_json", "platform_context_json"):
                    result[key.removesuffix("_json")] = json.loads(result.pop(key) or ("[]" if key in {"topics_json", "platform_tags_json", "image_urls_json"} else "{}"))
                sources = connection.execute(
                    """
                    SELECT source_type, source_ref, first_seen_at, last_seen_at
                    FROM content_source WHERE content_id = ?
                    ORDER BY last_seen_at DESC
                    """,
                    (content_id,),
                ).fetchall()
                hits = connection.execute(
                    """
                    SELECT platform_comment_id, comment_text, comment_author, like_count,
                        matched_keyword, published_at, fetched_at
                    FROM comment_hit WHERE content_id = ?
                    ORDER BY fetched_at DESC, id DESC
                    """,
                    (content_id,),
                ).fetchall()
                result["sources"] = [dict(item) for item in sources]
                result["comment_hits"] = [dict(item) for item in hits]
                material = connection.execute(
                    "SELECT * FROM material_export WHERE content_id = ?",
                    (content_id,),
                ).fetchone()
                result["material_export"] = dict(material) if material else None
                if result["material_export"]:
                    result["material_export"]["material_tags"] = json.loads(
                        result["material_export"].pop("material_tags_json") or "[]"
                    )
                return result

        def queue_material_export(
            self,
            *,
            content_id: int,
            library_type: str,
            rating: str | None,
            material_tags: list[str],
            note: str | None,
            selected_reason: str | None,
        ) -> dict[str, Any]:
            now = _now_iso()
            with self.connection() as connection:
                content = connection.execute(
                    "SELECT central_content_id FROM content WHERE id = ?",
                    (content_id,),
                ).fetchone()
                if not content:
                    raise ValueError("local content not found")
                connection.execute(
                    """
                    INSERT INTO material_export(
                        content_id, central_content_id, status, library_type, rating,
                        material_tags_json, note, selected_reason, created_at, updated_at
                    ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(content_id) DO UPDATE SET
                        central_content_id = COALESCE(excluded.central_content_id, material_export.central_content_id),
                        status = 'pending',
                        library_type = excluded.library_type,
                        rating = excluded.rating,
                        material_tags_json = excluded.material_tags_json,
                        note = excluded.note,
                        selected_reason = excluded.selected_reason,
                        last_error = NULL,
                        updated_at = excluded.updated_at
                    """,
                    (
                        content_id,
                        content["central_content_id"],
                        library_type,
                        rating,
                        _json(material_tags),
                        note,
                        selected_reason,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE content SET processing_status = 'material' WHERE id = ?",
                    (content_id,),
                )
                connection.commit()
            return self.get_material_export(content_id) or {}

        def get_material_export(self, content_id: int) -> dict[str, Any] | None:
            with self.connection() as connection:
                row = connection.execute(
                    "SELECT * FROM material_export WHERE content_id = ?",
                    (content_id,),
                ).fetchone()
                if not row:
                    return None
                result = dict(row)
                result["material_tags"] = json.loads(result.pop("material_tags_json") or "[]")
                return result

        def list_pending_material_exports(self, *, limit: int = 20) -> list[dict[str, Any]]:
            with self.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT me.*, c.central_content_id AS current_central_content_id
                    FROM material_export me
                    JOIN content c ON c.id = me.content_id
                    WHERE me.status IN ('pending', 'failed')
                    ORDER BY me.updated_at ASC, me.id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                results = []
                for row in rows:
                    item = dict(row)
                    item["central_content_id"] = item["current_central_content_id"] or item["central_content_id"]
                    item.pop("current_central_content_id", None)
                    item["material_tags"] = json.loads(item.pop("material_tags_json") or "[]")
                    results.append(item)
                return results

        def mark_material_export_synced(
            self,
            *,
            content_id: int,
            central_reference_item_id: str,
        ) -> None:
            now = _now_iso()
            with self.connection() as connection:
                connection.execute(
                    """
                    UPDATE material_export
                    SET status = 'synced', central_reference_item_id = ?,
                        last_error = NULL, synced_at = ?, updated_at = ?
                    WHERE content_id = ?
                    """,
                    (central_reference_item_id, now, now, content_id),
                )
                connection.commit()

        def mark_material_export_failed(self, *, content_id: int, error: str) -> None:
            with self.connection() as connection:
                connection.execute(
                    """
                    UPDATE material_export
                    SET status = 'failed', last_error = ?, updated_at = ?
                    WHERE content_id = ?
                    """,
                    (error, _now_iso(), content_id),
                )
                connection.commit()

        def _task_new_content_count(self, connection: sqlite3.Connection, task: dict[str, Any]) -> int:
            if task.get("task_type") != "creator_monitor":
                return 0
            since = task.get("last_viewed_at") or task.get("created_at")
            return int(
                connection.execute(
                    """
                    SELECT COUNT(DISTINCT cs.content_id)
                    FROM content_source cs
                    WHERE cs.source_type = 'creator'
                      AND cs.source_ref = ?
                      AND cs.first_seen_at > ?
                    """,
                    (task.get("target") or "", since),
                ).fetchone()[0]
            )

        @classmethod
        def _next_run_at(cls, task: dict[str, Any]) -> str | None:
            if not task.get("schedule_seconds") or task.get("status") == "paused":
                return None
            base = cls._parse_datetime(task.get("last_run_at")) or cls._parse_datetime(task.get("created_at"))
            if not base:
                return None
            return (base + timedelta(seconds=int(task["schedule_seconds"]))).isoformat()

        @staticmethod
        def _parse_datetime(value: str | None) -> datetime | None:
            if not value:
                return None
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
