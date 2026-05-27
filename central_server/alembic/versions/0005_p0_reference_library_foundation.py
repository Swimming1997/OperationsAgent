"""p0 reference library foundation

Revision ID: 0005_p0_reference_library
Revises: 0004_task_runs_observability
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa
from uuid import uuid4


revision = "0005_p0_reference_library"
down_revision = "0004_task_runs_observability"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(item["name"] == column for item in inspector.get_columns(table))


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table)}


def upgrade() -> None:
    if _has_table("reference_library_items"):
        if not _has_column("reference_library_items", "selection_sources_json"):
            op.add_column("reference_library_items", sa.Column("selection_sources_json", sa.JSON(), nullable=False, server_default="[]"))
        if not _has_column("reference_library_items", "matched_keywords_json"):
            op.add_column("reference_library_items", sa.Column("matched_keywords_json", sa.JSON(), nullable=False, server_default="[]"))
        if not _has_column("reference_library_items", "selected_at"):
            op.add_column("reference_library_items", sa.Column("selected_at", sa.DateTime(timezone=True)))

        conn = op.get_bind()
        conn.execute(sa.text("UPDATE reference_library_items SET selected_at = created_at WHERE selected_at IS NULL"))
        conn.execute(sa.text("UPDATE reference_library_items SET library_type = 'uncategorized' WHERE library_type IN ('benchmark_work', 'visual_material')"))
        conn.execute(sa.text("UPDATE reference_library_items SET library_type = 'lead' WHERE library_type = 'lead_case'"))
        conn.execute(sa.text("UPDATE reference_library_items SET rating = 'good' WHERE rating IN ('S', 'A')"))
        conn.execute(sa.text("UPDATE reference_library_items SET rating = 'medium' WHERE rating = 'B'"))
        conn.execute(sa.text("UPDATE reference_library_items SET rating = 'poor' WHERE rating = 'C'"))

        duplicate_rows = list(
            conn.execute(
                sa.text(
                    """
                    SELECT content_id
                    FROM reference_library_items
                    WHERE status = 'active'
                    GROUP BY content_id
                    HAVING COUNT(*) > 1
                    """
                )
            )
        )
        for (content_id,) in duplicate_rows:
            rows = list(
                conn.execute(
                    sa.text(
                        """
                        SELECT id
                        FROM reference_library_items
                        WHERE content_id = :content_id AND status = 'active'
                        ORDER BY selected_at DESC, created_at DESC
                        """
                    ),
                    {"content_id": content_id},
                )
            )
            for (item_id,) in rows[1:]:
                conn.execute(
                    sa.text("UPDATE reference_library_items SET status = 'archived', usage_status = 'archived' WHERE id = :item_id"),
                    {"item_id": item_id},
                )
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO reference_library_events
                            (id, library_item_id, content_id, event_type, event_payload_json, created_at)
                        VALUES
                            (:id, :library_item_id, :content_id, 'archived', :payload, CURRENT_TIMESTAMP)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "library_item_id": item_id,
                        "content_id": content_id,
                        "payload": '{"reason":"dedupe_active_content"}',
                    },
                )

        indexes = _index_names("reference_library_items")
        if "uq_reference_library_active_content_type" in indexes:
            op.drop_index("uq_reference_library_active_content_type", table_name="reference_library_items")
        if "uq_reference_library_active_content" not in indexes:
            op.create_index(
                "uq_reference_library_active_content",
                "reference_library_items",
                ["content_id"],
                unique=True,
                sqlite_where=sa.text("status = 'active'"),
                postgresql_where=sa.text("status = 'active'"),
            )
        if "idx_reference_library_selected_at" not in indexes:
            op.create_index("idx_reference_library_selected_at", "reference_library_items", ["selected_at"])
        if "idx_reference_library_type_status" not in indexes:
            op.create_index("idx_reference_library_type_status", "reference_library_items", ["library_type", "status"])

    if not _has_table("rule_profiles"):
        op.create_table(
            "rule_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("library_type", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "uq_rule_profile_enabled_scope",
            "rule_profiles",
            ["platform", "library_type"],
            unique=True,
            sqlite_where=sa.text("enabled = 1"),
            postgresql_where=sa.text("enabled = true"),
        )
        op.create_index("idx_rule_profiles_scope", "rule_profiles", ["platform", "library_type", "enabled"])


def downgrade() -> None:
    indexes = _index_names("reference_library_items")
    if "idx_reference_library_type_status" in indexes:
        op.drop_index("idx_reference_library_type_status", table_name="reference_library_items")
    if "idx_reference_library_selected_at" in indexes:
        op.drop_index("idx_reference_library_selected_at", table_name="reference_library_items")
    if "uq_reference_library_active_content" in indexes:
        op.drop_index("uq_reference_library_active_content", table_name="reference_library_items")
    if _has_table("rule_profiles"):
        op.drop_table("rule_profiles")
