"""task template business type, operator ownership, runtime executor

Revision ID: 0012_task_template_business_type_and_operator
Revises: 0011_user_intelligence_scenario_filters
Create Date: 2026-05-30
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0012_task_template_business_type_and_operator"
down_revision = "0011_user_intelligence_scenario_filters"
branch_labels = None
depends_on = None


def _strip_executor_from_config(raw: str | None) -> str | None:
    if not raw:
        return raw
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return raw
    if not isinstance(data, dict):
        return raw
    data.pop("executor_account_id", None)
    return json.dumps(data, ensure_ascii=False)


def upgrade() -> None:
    op.add_column("task_templates", sa.Column("created_by_user_id", sa.String(length=36), nullable=True))
    op.add_column("task_runs", sa.Column("executor_account_id", sa.String(length=36), nullable=True))
    op.add_column("task_schedules", sa.Column("executor_account_id", sa.String(length=36), nullable=True))
    op.add_column("task_schedules", sa.Column("created_by_user_id", sa.String(length=36), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_task_templates_created_by_user_id_users",
            "task_templates",
            "users",
            ["created_by_user_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_task_runs_executor_account_id_platform_accounts",
            "task_runs",
            "platform_accounts",
            ["executor_account_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_task_schedules_executor_account_id_platform_accounts",
            "task_schedules",
            "platform_accounts",
            ["executor_account_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_task_schedules_created_by_user_id_users",
            "task_schedules",
            "users",
            ["created_by_user_id"],
            ["id"],
        )

    # Backfill business_account_type_id from account_id or config executor_account_id
    bind.execute(
        sa.text(
            """
            UPDATE task_templates
            SET business_account_type_id = (
                SELECT a.business_account_type_id
                FROM platform_accounts a
                WHERE a.id = COALESCE(
                    task_templates.account_id,
                    json_extract(task_templates.config_json, '$.executor_account_id')
                )
            )
            WHERE business_account_type_id IS NULL
              AND COALESCE(
                    task_templates.account_id,
                    json_extract(task_templates.config_json, '$.executor_account_id')
                ) IS NOT NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE task_templates
            SET enabled = 0
            WHERE business_account_type_id IS NULL
            """
        )
    )

    # Backfill schedule executor from template legacy fields
    bind.execute(
        sa.text(
            """
            UPDATE task_schedules
            SET executor_account_id = (
                SELECT COALESCE(
                    t.account_id,
                    json_extract(t.config_json, '$.executor_account_id')
                )
                FROM task_templates t
                WHERE t.id = task_schedules.task_template_id
            )
            WHERE executor_account_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE task_schedules
            SET enabled = 0
            WHERE executor_account_id IS NULL
            """
        )
    )

    rows = bind.execute(sa.text("SELECT id, config_json FROM task_templates")).fetchall()
    for row in rows:
        template_id, config_raw = row[0], row[1]
        stripped = _strip_executor_from_config(config_raw)
        if stripped != config_raw:
            bind.execute(
                sa.text("UPDATE task_templates SET config_json = :cfg WHERE id = :id"),
                {"cfg": stripped, "id": template_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_task_schedules_created_by_user_id_users", "task_schedules", type_="foreignkey")
        op.drop_constraint("fk_task_schedules_executor_account_id_platform_accounts", "task_schedules", type_="foreignkey")
        op.drop_constraint("fk_task_runs_executor_account_id_platform_accounts", "task_runs", type_="foreignkey")
        op.drop_constraint("fk_task_templates_created_by_user_id_users", "task_templates", type_="foreignkey")
    op.drop_column("task_schedules", "created_by_user_id")
    op.drop_column("task_schedules", "executor_account_id")
    op.drop_column("task_runs", "executor_account_id")
    op.drop_column("task_templates", "created_by_user_id")
