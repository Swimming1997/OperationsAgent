from sqlalchemy import inspect, text

from intelligence_engine.db.base import Base
from intelligence_engine.db.models import *  # noqa: F403
from intelligence_engine.db.session import SessionLocal, engine
from intelligence_engine.storage.repositories.product_repository import ProductRepository


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    with SessionLocal() as db:
        ProductRepository(db).ensure_default_roles()
        db.commit()


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "jobs" in table_names:
        job_columns = {column["name"] for column in inspector.get_columns("jobs")}
        if "task_run_id" not in job_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN task_run_id VARCHAR(36)"))
    if "platform_accounts" in table_names:
        account_columns = {column["name"] for column in inspector.get_columns("platform_accounts")}
        account_alters = {
            "auth_status": "ALTER TABLE platform_accounts ADD COLUMN auth_status VARCHAR(32) DEFAULT 'not_logged_in' NOT NULL",
            "profile_key": "ALTER TABLE platform_accounts ADD COLUMN profile_key VARCHAR(255)",
            "platform_nickname": "ALTER TABLE platform_accounts ADD COLUMN platform_nickname VARCHAR(255)",
            "platform_home_url": "ALTER TABLE platform_accounts ADD COLUMN platform_home_url VARCHAR(512)",
            "last_verified_at": "ALTER TABLE platform_accounts ADD COLUMN last_verified_at DATETIME",
            "login_cdp_port": "ALTER TABLE platform_accounts ADD COLUMN login_cdp_port INTEGER",
            "account_role": "ALTER TABLE platform_accounts ADD COLUMN account_role VARCHAR(64) DEFAULT 'intelligence_collector' NOT NULL",
            "health_status": "ALTER TABLE platform_accounts ADD COLUMN health_status VARCHAR(64) DEFAULT 'healthy' NOT NULL",
        }
        with engine.begin() as conn:
            for name, ddl in account_alters.items():
                if name not in account_columns:
                    conn.execute(text(ddl))
