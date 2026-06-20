"""P2 hot path indexes

Revision ID: 0015_p2_hot_path_indexes
Revises: 0014_manual_tag_registry
Create Date: 2026-06-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_p2_hot_path_indexes"
down_revision = "0014_manual_tag_registry"
branch_labels = None
depends_on = None


INDEXES = (
    ("idx_task_schedules_enabled_next_run", "task_schedules", ["enabled", "next_run_at"]),
)


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table)}


def upgrade() -> None:
    for name, table, columns in INDEXES:
        if name not in _index_names(table):
            op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        if name in _index_names(table):
            op.drop_index(name, table_name=table)
