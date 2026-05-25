"""task center and intelligence workflow

Revision ID: 0003_task_workflow
Revises: 0002_product_phase_a
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_task_workflow"
down_revision = "0002_product_phase_a"
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
    if not _has_column("task_schedules", "last_materialized_at"):
        op.add_column("task_schedules", sa.Column("last_materialized_at", sa.DateTime(timezone=True)))

    if not _has_table("content_workflow_states"):
        op.create_table(
            "content_workflow_states",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("content_id", sa.String(length=36), sa.ForeignKey("content_identity.id"), nullable=False, unique=True),
            sa.Column("workflow_status", sa.String(length=64), nullable=False, server_default="pending_review"),
            sa.Column("assigned_to_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("assigned_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("assigned_at", sa.DateTime(timezone=True)),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
            sa.Column("selected_at", sa.DateTime(timezone=True)),
            sa.Column("discarded_at", sa.DateTime(timezone=True)),
            sa.Column("latest_operator_note", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_content_workflow_status", "content_workflow_states", ["workflow_status"])
        op.create_index("idx_content_workflow_assignee", "content_workflow_states", ["assigned_to_user_id"])

    if not _has_table("content_assignments"):
        op.create_table(
            "content_assignments",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("content_id", sa.String(length=36), sa.ForeignKey("content_identity.id"), nullable=False),
            sa.Column("assigned_to_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assigned_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False, server_default="assigned"),
            sa.Column("remark", sa.Text()),
        )
        op.create_index("idx_content_assignments_content_id", "content_assignments", ["content_id"])

    if not _has_table("content_operator_notes"):
        op.create_table(
            "content_operator_notes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("content_id", sa.String(length=36), sa.ForeignKey("content_identity.id"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_content_notes_content_id", "content_operator_notes", ["content_id"])

    if not _has_table("business_account_type_rule_sets"):
        op.create_table(
            "business_account_type_rule_sets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("business_account_type_id", sa.String(length=36), sa.ForeignKey("business_account_types.id"), nullable=False),
            sa.Column("rule_set_id", sa.String(length=36), sa.ForeignKey("keyword_rule_sets.id"), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("business_account_type_id", "rule_set_id", name="uq_bat_rule_set"),
        )


def downgrade() -> None:
    for table in ("business_account_type_rule_sets", "content_operator_notes", "content_assignments", "content_workflow_states"):
        if _has_table(table):
            op.drop_table(table)
