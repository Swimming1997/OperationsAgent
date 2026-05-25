"""task runs observability

Revision ID: 0004_task_runs_observability
Revises: 0003_task_workflow
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_task_runs_observability"
down_revision = "0003_task_workflow"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_table("task_runs"):
        op.create_table(
            "task_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("task_template_id", sa.String(length=36), sa.ForeignKey("task_templates.id"), nullable=False),
            sa.Column("trigger_type", sa.String(length=32), nullable=False),
            sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("task_schedule_id", sa.String(length=36), sa.ForeignKey("task_schedules.id")),
            sa.Column("status", sa.String(length=64), nullable=False, server_default="materialized"),
            sa.Column("jobs_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("jobs_pending", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("jobs_running", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("jobs_success", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("jobs_failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("result_summary_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("error_summary_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
        )
        op.create_index("idx_task_runs_template_created", "task_runs", ["task_template_id", "created_at"])
        op.create_index("idx_task_runs_status", "task_runs", ["status"])

    if not _has_column("jobs", "task_run_id"):
        op.add_column("jobs", sa.Column("task_run_id", sa.String(length=36), sa.ForeignKey("task_runs.id")))
        op.create_index("idx_jobs_task_run_id", "jobs", ["task_run_id"])


def downgrade() -> None:
    if _has_column("jobs", "task_run_id"):
        op.drop_index("idx_jobs_task_run_id", table_name="jobs")
        op.drop_column("jobs", "task_run_id")
    if _has_table("task_runs"):
        op.drop_table("task_runs")
