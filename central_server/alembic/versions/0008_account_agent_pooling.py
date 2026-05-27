"""account agent pooling

Revision ID: 0008_account_agent_pooling
Revises: 0007_operation_rules
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_account_agent_pooling"
down_revision = "0007_operation_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_agent_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.String(length=36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["platform_accounts.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["local_agents.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "agent_id", name="uq_account_agent_binding"),
    )
    op.create_index("idx_account_agent_bindings_account", "account_agent_bindings", ["account_id"])
    op.create_index("idx_account_agent_bindings_agent", "account_agent_bindings", ["agent_id"])
    op.create_index("idx_account_agent_bindings_employee", "account_agent_bindings", ["employee_id"])

def downgrade() -> None:
    op.drop_index("idx_account_agent_bindings_employee", table_name="account_agent_bindings")
    op.drop_index("idx_account_agent_bindings_agent", table_name="account_agent_bindings")
    op.drop_index("idx_account_agent_bindings_account", table_name="account_agent_bindings")
    op.drop_table("account_agent_bindings")
