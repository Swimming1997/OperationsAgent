from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from intelligence_engine.config import Settings
from intelligence_engine.db.models import ContentIdentity, ContentSnapshot
from intelligence_engine.db.session import get_db
from intelligence_engine.domain.enums import ContentType, Platform
from intelligence_engine.main import create_app
from intelligence_engine.services.media_service import COVER_MEDIA_PROXY_OK, COVER_MEDIA_STORED, COVER_MEDIA_UNAVAILABLE, MediaService


@pytest.fixture
def media_settings(tmp_path: Path) -> Settings:
    return Settings(
        media_root=str(tmp_path / "media"),
        media_signing_secret="test-media-secret",
        media_allowed_hosts="xhscdn.com,invalid.local",
        media_fetch_timeout_seconds=5.0,
    )


def test_is_allowed_media_url(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    assert media.is_allowed_media_url("https://sns-webpic-qc.xhscdn.com/abc/cover.jpg")
    assert not media.is_allowed_media_url("https://evil.example/cover.jpg")
    assert not media.is_allowed_media_url(None)


def test_sign_and_verify_cover_token(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    expires, signature = media.sign_cover_token("content-1", expires_at=9_999_999_999)
    assert media.verify_cover_token("content-1", expires, signature)
    assert not media.verify_cover_token("content-1", 1, signature)


def test_build_cover_display_url_requires_cover(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    assert media.build_cover_display_url("content-1", cover_url="https://sns-webpic-qc.xhscdn.com/a.jpg") is not None
    assert media.build_cover_display_url("content-1") is None


def test_resolve_after_detail_ingest_prefers_local_store(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    snapshot = ContentSnapshot(
        content_id="content-1",
        cover_url="https://sns-webpic-qc.xhscdn.com/a.jpg",
        image_urls_json=[],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    with patch.object(media, "download_cover", return_value=(b"image-bytes", "image/jpeg")):
        media.resolve_after_detail_ingest(snapshot)
    assert snapshot.cover_media_status == COVER_MEDIA_STORED
    assert snapshot.stored_cover_path == "content-1/cover.jpg"


def test_resolve_after_detail_ingest_proxy_ok_when_download_fails(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    snapshot = ContentSnapshot(
        content_id="content-1",
        cover_url="https://sns-webpic-qc.xhscdn.com/a.jpg",
        image_urls_json=[],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    with patch.object(media, "download_cover", return_value=None), patch.object(media, "probe_cover_url", return_value=True):
        media.resolve_after_detail_ingest(snapshot)
    assert snapshot.cover_media_status == COVER_MEDIA_PROXY_OK
    assert snapshot.stored_cover_path is None


def test_resolve_after_detail_ingest_uses_image_urls_when_cover_missing(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    snapshot = ContentSnapshot(
        content_id="content-1",
        cover_url=None,
        image_urls_json=["https://sns-webpic-qc.xhscdn.com/fallback.jpg"],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    with patch.object(media, "download_cover", return_value=(b"image-bytes", "image/jpeg")) as download:
        media.resolve_after_detail_ingest(snapshot)
    download.assert_called_once_with("https://sns-webpic-qc.xhscdn.com/fallback.jpg")
    assert snapshot.cover_url == "https://sns-webpic-qc.xhscdn.com/fallback.jpg"
    assert snapshot.cover_media_status == COVER_MEDIA_STORED


def test_build_cover_display_url_falls_back_to_metadata_and_image_urls(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    snapshot = ContentSnapshot(
        content_id="content-1",
        cover_url=None,
        image_urls_json=["https://sns-webpic-qc.xhscdn.com/from-images.jpg"],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    assert media.build_cover_display_url_for_snapshot("content-1", snapshot, {"cover_url": "https://sns-webpic-qc.xhscdn.com/meta.jpg"}) is not None
    assert media.resolve_effective_cover_url(snapshot, {"cover_url": "https://sns-webpic-qc.xhscdn.com/meta.jpg"}) == "https://sns-webpic-qc.xhscdn.com/from-images.jpg"


def test_resolve_after_detail_ingest_stores_on_probe_failure(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    snapshot = ContentSnapshot(
        content_id="content-1",
        cover_url="https://sns-webpic-qc.xhscdn.com/a.jpg",
        image_urls_json=[],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    with patch.object(media, "probe_cover_url", return_value=False), patch.object(
        media, "download_cover", return_value=(b"image-bytes", "image/jpeg")
    ):
        media.resolve_after_detail_ingest(snapshot)
    assert snapshot.cover_media_status == COVER_MEDIA_STORED
    assert snapshot.stored_cover_path == "content-1/cover.jpg"
    assert (media.media_root() / snapshot.stored_cover_path).is_file()


def test_resolve_after_detail_ingest_unavailable_without_cover(media_settings: Settings) -> None:
    media = MediaService(media_settings)
    snapshot = ContentSnapshot(
        content_id="content-1",
        cover_url=None,
        image_urls_json=[],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    media.resolve_after_detail_ingest(snapshot)
    assert snapshot.cover_media_status == COVER_MEDIA_UNAVAILABLE


def test_media_cover_route_serves_stored_file(db_session, media_settings: Settings, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INTEL_ENGINE_MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("INTEL_ENGINE_MEDIA_SIGNING_SECRET", "test-media-secret")
    from intelligence_engine.config import get_settings

    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    content = ContentIdentity(
        platform=Platform.XHS.value,
        platform_content_id="note-media-1",
        canonical_url="https://www.xiaohongshu.com/explore/note-media-1",
        content_type=ContentType.IMAGE_TEXT.value,
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        metadata_json={},
    )
    db_session.add(content)
    db_session.flush()

    media = MediaService()
    stored_path = media.persist_cover(content.id, b"stored-cover", "image/png")
    snapshot = ContentSnapshot(
        content_id=content.id,
        cover_url="https://sns-webpic-qc.xhscdn.com/a.jpg",
        stored_cover_path=stored_path,
        cover_media_status=COVER_MEDIA_STORED,
        image_urls_json=[],
        raw_payload_json={},
        fetched_at=datetime.now(timezone.utc),
    )
    db_session.add(snapshot)
    db_session.flush()
    content.latest_snapshot_id = snapshot.id
    db_session.commit()

    expires, signature = media.sign_cover_token(content.id, expires_at=9_999_999_999)
    client = TestClient(app)
    response = client.get(f"/api/media/cover/{content.id}?e={expires}&s={signature}")
    assert response.status_code == 200
    assert response.content == b"stored-cover"
    assert response.headers["content-type"].startswith("image/png")
    get_settings.cache_clear()


def test_media_cover_route_rejects_invalid_signature(db_session, media_settings: Settings) -> None:
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    response = client.get("/api/media/cover/missing?e=9999999999&s=bad")
    assert response.status_code == 403
