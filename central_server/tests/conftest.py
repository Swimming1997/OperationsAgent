import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from intelligence_engine.db.base import Base
from intelligence_engine.db import models  # noqa: F401


@pytest.fixture(autouse=True)
def reset_intelligence_settings(monkeypatch):
    from intelligence_engine.config import get_settings

    monkeypatch.setenv("INTEL_ENGINE_ALLOW_HEADER_AUTH", "true")
    for name in (
        "INTEL_ENGINE_ENQUEUE_DETAIL_POLICY",
        "INTEL_ENGINE_ENQUEUE_COMMENT_POLICY",
        "INTEL_ENGINE_COMMENT_AUTO_COUNT_THRESHOLD",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session(tmp_path):
    database_url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
