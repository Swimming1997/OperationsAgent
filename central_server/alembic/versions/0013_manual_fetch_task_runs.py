"""manual fetch task runs

Revision ID: 0013_manual_fetch_task_runs
Revises: 0012_task_template_business_type_and_operator
Create Date: 2026-05-31
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0013_manual_fetch_task_runs"
down_revision = "0012_task_template_business_type_and_operator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_runs") as batch_op:
        batch_op.alter_column("task_template_id", existing_type=sa.String(length=36), nullable=True)
    _backfill_manual_fetch_runs()


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE jobs SET task_run_id = NULL WHERE task_run_id IN (SELECT id FROM task_runs WHERE task_template_id IS NULL)"))
    bind.execute(sa.text("DELETE FROM task_runs WHERE task_template_id IS NULL"))
    with op.batch_alter_table("task_runs") as batch_op:
        batch_op.alter_column("task_template_id", existing_type=sa.String(length=36), nullable=False)


def _backfill_manual_fetch_runs() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, account_id, payload_json, created_at, updated_at
            FROM jobs
            WHERE task_run_id IS NULL
              AND job_type IN ('detail_fetch', 'comment_fetch')
            """
        )
    ).fetchall()
    for row in rows:
        payload = _coerce_payload(row.payload_json)
        if payload.get("manual_enqueue") is not True:
            continue
        run_id = str(uuid4())
        created_at = _coerce_datetime(row.created_at)
        updated_at = _coerce_datetime(row.updated_at) or created_at
        bind.execute(
            sa.text(
                """
                INSERT INTO task_runs (
                    id, task_template_id, trigger_type, requested_by_user_id,
                    executor_account_id, task_schedule_id, status,
                    jobs_total, jobs_pending, jobs_running, jobs_success, jobs_failed,
                    result_summary_json, error_summary_json, finished_at, created_at, updated_at
                ) VALUES (
                    :id, NULL, 'manual', NULL,
                    :executor_account_id, NULL, 'materialized',
                    0, 0, 0, 0, 0,
                    :result_summary_json, :error_summary_json, NULL, :created_at, :updated_at
                )
                """
            ),
            {
                "id": run_id,
                "executor_account_id": row.account_id,
                "result_summary_json": "{}",
                "error_summary_json": "{}",
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        bind.execute(sa.text("UPDATE jobs SET task_run_id = :run_id WHERE id = :job_id"), {"run_id": run_id, "job_id": row.id})


def _coerce_datetime(value) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return datetime.now(timezone.utc).isoformat()


def _coerce_payload(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
