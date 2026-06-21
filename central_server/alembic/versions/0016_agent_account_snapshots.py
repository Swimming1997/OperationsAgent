"""agent account snapshots (read-only monitoring mirror)

Revision ID: 0016_agent_account_snapshots
Revises: 0015_p2_hot_path_indexes
Create Date: 2026-06-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_agent_account_snapshots"
down_revision = "0015_p2_hot_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_account_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("local_account_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("platform_nickname", sa.String(length=255), nullable=True),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("account_role", sa.String(length=64), nullable=False, server_default="intelligence_collector"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("auth_status", sa.String(length=32), nullable=False, server_default="not_logged_in"),
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["local_agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "local_account_id", name="uq_agent_account_snapshot"),
    )
    op.create_index("idx_agent_account_snapshots_agent", "agent_account_snapshots", ["agent_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_account_snapshots_agent", table_name="agent_account_snapshots")
    op.drop_table("agent_account_snapshots")
