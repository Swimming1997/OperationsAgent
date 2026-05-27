"""intelligence list performance indexes

Revision ID: 0006_intelligence_perf_indexes
Revises: 0005_p0_reference_library
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_intelligence_perf_indexes"
down_revision = "0005_p0_reference_library"
branch_labels = None
depends_on = None


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table)}


def upgrade() -> None:
    discovery_indexes = _index_names("content_discovery_events")
    if "idx_discovery_content_discovered_at" not in discovery_indexes:
        op.create_index(
            "idx_discovery_content_discovered_at",
            "content_discovery_events",
            ["content_id", "discovered_at"],
        )
    reference_indexes = _index_names("reference_library_items")
    if "idx_reference_library_content_status" not in reference_indexes:
        op.create_index(
            "idx_reference_library_content_status",
            "reference_library_items",
            ["content_id", "status"],
        )


def downgrade() -> None:
    reference_indexes = _index_names("reference_library_items")
    if "idx_reference_library_content_status" in reference_indexes:
        op.drop_index("idx_reference_library_content_status", table_name="reference_library_items")
    discovery_indexes = _index_names("content_discovery_events")
    if "idx_discovery_content_discovered_at" in discovery_indexes:
        op.drop_index("idx_discovery_content_discovered_at", table_name="content_discovery_events")
