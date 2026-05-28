"""add submitter fields to keyword_rule_sets

Revision ID: 0009_operator_rule_submitter_fields
Revises: 0008_account_agent_pooling
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_operator_rule_submitter_fields"
down_revision = "0008_account_agent_pooling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("keyword_rule_sets", sa.Column("created_by_user_id", sa.String(length=36), nullable=True))
    op.add_column("keyword_rule_sets", sa.Column("created_by_employee_id", sa.String(length=36), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_keyword_rule_sets_created_by_user_id_users",
            "keyword_rule_sets",
            "users",
            ["created_by_user_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_keyword_rule_sets_created_by_employee_id_employees",
            "keyword_rule_sets",
            "employees",
            ["created_by_employee_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_keyword_rule_sets_created_by_employee_id_employees", "keyword_rule_sets", type_="foreignkey")
        op.drop_constraint("fk_keyword_rule_sets_created_by_user_id_users", "keyword_rule_sets", type_="foreignkey")
    op.drop_column("keyword_rule_sets", "created_by_employee_id")
    op.drop_column("keyword_rule_sets", "created_by_user_id")
