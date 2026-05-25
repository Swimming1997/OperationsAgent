"""initial intelligence engine schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-18
"""

from alembic import op

from intelligence_engine.db.base import Base
from intelligence_engine.db import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
