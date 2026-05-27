"""operation rules (P1)

Revision ID: 0007_operation_rules
Revises: 0006_intelligence_perf_indexes
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_operation_rules"
down_revision = "0006_intelligence_perf_indexes"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table)}


def upgrade() -> None:
    if _has_table("operation_rules"):
        return
    op.create_table(
        "operation_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    indexes = _index_names("operation_rules")
    if "idx_operation_rules_type_platform" not in indexes:
        op.create_index("idx_operation_rules_type_platform", "operation_rules", ["rule_type", "platform"])
    if "idx_operation_rules_enabled" not in indexes:
        op.create_index("idx_operation_rules_enabled", "operation_rules", ["enabled"])


def downgrade() -> None:
    op.drop_index("idx_operation_rules_enabled", table_name="operation_rules")
    op.drop_index("idx_operation_rules_type_platform", table_name="operation_rules")
    op.drop_table("operation_rules")
