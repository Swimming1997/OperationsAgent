"""product upper layer phase a

Revision ID: 0002_product_phase_a
Revises: 0001_initial
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_product_phase_a"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("username", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("email", sa.String(length=255)),
            sa.Column("password_hash", sa.String(length=255)),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("uq_users_email_not_null", "users", ["email"], unique=True, sqlite_where=sa.text("email IS NOT NULL"), postgresql_where=sa.text("email IS NOT NULL"))
        op.create_index("idx_users_status", "users", ["status"])

    if not _has_table("roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False, unique=True),
            sa.Column("description", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _has_table("user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role_id", sa.String(length=36), sa.ForeignKey("roles.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        )

    if not _has_table("business_account_types"):
        op.create_table(
            "business_account_types",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("description", sa.Text()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _has_column("employees", "user_id"):
        op.add_column("employees", sa.Column("user_id", sa.String(length=36)))
        op.create_index("idx_employees_user_id", "employees", ["user_id"])
        op.create_index("uq_employees_user_id", "employees", ["user_id"], unique=True)

    if not _has_column("platform_accounts", "business_account_type_id"):
        op.add_column("platform_accounts", sa.Column("business_account_type_id", sa.String(length=36)))
        op.create_index("idx_platform_accounts_business_type_id", "platform_accounts", ["business_account_type_id"])

    if not _has_table("benchmark_groups"):
        op.create_table(
            "benchmark_groups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("owner_employee_id", sa.String(length=36), sa.ForeignKey("employees.id")),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_benchmark_groups_enabled", "benchmark_groups", ["enabled"])

    if not _has_table("benchmark_group_members"):
        op.create_table(
            "benchmark_group_members",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("benchmark_group_id", sa.String(length=36), sa.ForeignKey("benchmark_groups.id"), nullable=False),
            sa.Column("creator_monitor_id", sa.String(length=36), sa.ForeignKey("creator_monitors.id")),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("creator_platform_id", sa.String(length=255)),
            sa.Column("creator_profile_url", sa.Text()),
            sa.Column("display_name", sa.String(length=255)),
            sa.Column("platform_context_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_benchmark_members_group_id", "benchmark_group_members", ["benchmark_group_id"])
        op.create_index("uq_benchmark_group_creator", "benchmark_group_members", ["benchmark_group_id", "platform", "creator_platform_id"], unique=True, sqlite_where=sa.text("creator_platform_id IS NOT NULL"), postgresql_where=sa.text("creator_platform_id IS NOT NULL"))

    if not _has_table("business_account_type_benchmark_groups"):
        op.create_table(
            "business_account_type_benchmark_groups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("business_account_type_id", sa.String(length=36), sa.ForeignKey("business_account_types.id"), nullable=False),
            sa.Column("benchmark_group_id", sa.String(length=36), sa.ForeignKey("benchmark_groups.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("business_account_type_id", "benchmark_group_id", name="uq_bat_benchmark_group"),
        )

    if not _has_table("task_templates"):
        op.create_table(
            "task_templates",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("template_type", sa.String(length=64), nullable=False),
            sa.Column("platform", sa.String(length=32)),
            sa.Column("account_id", sa.String(length=36), sa.ForeignKey("platform_accounts.id")),
            sa.Column("business_account_type_id", sa.String(length=36), sa.ForeignKey("business_account_types.id")),
            sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_task_templates_type_enabled", "task_templates", ["template_type", "enabled"])

    if not _has_table("task_schedules"):
        op.create_table(
            "task_schedules",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("task_template_id", sa.String(length=36), sa.ForeignKey("task_templates.id"), nullable=False),
            sa.Column("schedule_type", sa.String(length=64), nullable=False),
            sa.Column("interval_seconds", sa.Integer()),
            sa.Column("daily_time_window_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("next_run_at", sa.DateTime(timezone=True)),
            sa.Column("last_run_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_task_schedules_template_id", "task_schedules", ["task_template_id"])
        op.create_index("idx_task_schedules_enabled", "task_schedules", ["enabled"])

    if not _has_table("behavior_profiles"):
        op.create_table(
            "behavior_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("description", sa.Text()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _has_table("network_egress_profiles"):
        op.create_table(
            "network_egress_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("strategy", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _has_table("risk_policies"):
        op.create_table(
            "risk_policies",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False, unique=True),
            sa.Column("description", sa.Text()),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("behavior_profile_id", sa.String(length=36), sa.ForeignKey("behavior_profiles.id")),
            sa.Column("network_egress_profile_id", sa.String(length=36), sa.ForeignKey("network_egress_profiles.id")),
            sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_risk_policies_enabled", "risk_policies", ["enabled"])


def downgrade() -> None:
    for table in (
        "risk_policies",
        "network_egress_profiles",
        "behavior_profiles",
        "task_schedules",
        "task_templates",
        "business_account_type_benchmark_groups",
        "benchmark_group_members",
        "benchmark_groups",
        "user_roles",
        "roles",
        "users",
        "business_account_types",
    ):
        if _has_table(table):
            op.drop_table(table)
