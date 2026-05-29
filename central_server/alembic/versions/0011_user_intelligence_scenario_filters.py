"""add user_intelligence_scenario_filters table

Revision ID: 0011_user_intelligence_scenario_filters
Revises: 0010_content_snapshot_stored_cover
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_user_intelligence_scenario_filters"
down_revision = "0010_content_snapshot_stored_cover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_intelligence_scenario_filters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("rolling_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scenario", name="uq_user_intelligence_scenario_filters_user_scenario"),
    )
    op.create_index(
        "idx_user_intelligence_scenario_filters_user_id",
        "user_intelligence_scenario_filters",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_intelligence_scenario_filters_user_id", table_name="user_intelligence_scenario_filters")
    op.drop_table("user_intelligence_scenario_filters")
