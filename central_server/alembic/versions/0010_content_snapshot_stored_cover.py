"""add stored cover fields to content_snapshots

Revision ID: 0010_content_snapshot_stored_cover
Revises: 0009_operator_rule_submitter_fields
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_content_snapshot_stored_cover"
down_revision = "0009_operator_rule_submitter_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_snapshots", sa.Column("stored_cover_path", sa.Text(), nullable=True))
    op.add_column("content_snapshots", sa.Column("cover_media_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("content_snapshots", "cover_media_status")
    op.drop_column("content_snapshots", "stored_cover_path")
