"""manual tag registry and content associations

Revision ID: 0014_manual_tag_registry
Revises: 0013_manual_fetch_task_runs
Create Date: 2026-05-31
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0014_manual_tag_registry"
down_revision = "0013_manual_fetch_task_runs"
branch_labels = None
depends_on = None

SYSTEM_TAG_WATCH_LATER = "稍后看"


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upgrade() -> None:
    op.create_table(
        "manual_tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_manual_tags_name"),
    )
    op.create_index("idx_manual_tags_status", "manual_tags", ["status"])

    op.create_table(
        "content_manual_tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content_identity.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["manual_tags.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "tag_id", name="uq_content_manual_tags_content_tag"),
    )
    op.create_index("idx_content_manual_tags_content_id", "content_manual_tags", ["content_id"])
    op.create_index("idx_content_manual_tags_tag_id", "content_manual_tags", ["tag_id"])

    bind = op.get_bind()
    now = _utcnow()
    watch_later_id = _new_uuid()
    bind.execute(
        sa.text(
            """
            INSERT INTO manual_tags (id, name, status, is_system, created_by_user_id, archived_at, archived_by_user_id, created_at, updated_at)
            VALUES (:id, :name, 'active', 1, NULL, NULL, NULL, :created_at, :updated_at)
            """
        ),
        {"id": watch_later_id, "name": SYSTEM_TAG_WATCH_LATER, "created_at": now, "updated_at": now},
    )

    tag_name_to_id: dict[str, str] = {SYSTEM_TAG_WATCH_LATER: watch_later_id}
    rows = bind.execute(sa.text("SELECT id, metadata_json FROM content_identity")).fetchall()
    for content_id, metadata_raw in rows:
        metadata = metadata_raw if isinstance(metadata_raw, dict) else json.loads(metadata_raw or "{}")
        manual_tags = metadata.get("manual_tags")
        if not isinstance(manual_tags, list):
            continue
        seen_names: set[str] = set()
        for raw_name in manual_tags:
            name = str(raw_name).strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            tag_id = tag_name_to_id.get(name)
            if not tag_id:
                tag_id = _new_uuid()
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO manual_tags (id, name, status, is_system, created_by_user_id, archived_at, archived_by_user_id, created_at, updated_at)
                        VALUES (:id, :name, 'active', 0, NULL, NULL, NULL, :created_at, :updated_at)
                        """
                    ),
                    {"id": tag_id, "name": name, "created_at": now, "updated_at": now},
                )
                tag_name_to_id[name] = tag_id
            bind.execute(
                sa.text(
                    """
                    INSERT INTO content_manual_tags (id, content_id, tag_id, created_at)
                    VALUES (:id, :content_id, :tag_id, :created_at)
                    """
                ),
                {"id": _new_uuid(), "content_id": content_id, "tag_id": tag_id, "created_at": now},
            )


def downgrade() -> None:
    op.drop_index("idx_content_manual_tags_tag_id", table_name="content_manual_tags")
    op.drop_index("idx_content_manual_tags_content_id", table_name="content_manual_tags")
    op.drop_table("content_manual_tags")
    op.drop_index("idx_manual_tags_status", table_name="manual_tags")
    op.drop_table("manual_tags")
