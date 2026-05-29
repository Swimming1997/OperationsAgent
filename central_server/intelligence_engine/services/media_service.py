from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from intelligence_engine.config import Settings, get_settings

if TYPE_CHECKING:
    from intelligence_engine.db.models import ContentSnapshot

COVER_MEDIA_PROXY_OK = "proxy_ok"
COVER_MEDIA_STORED = "stored"
COVER_MEDIA_UNAVAILABLE = "unavailable"

_CONTENT_TYPE_EXT = {
    "image/webp": "webp",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
}


class MediaService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._media_root = Path(self.settings.media_root).resolve()

    def media_root(self) -> Path:
        self._media_root.mkdir(parents=True, exist_ok=True)
        return self._media_root

    def is_allowed_media_url(self, url: str | None) -> bool:
        if not url or not str(url).strip():
            return False
        parsed = urlparse(str(url).strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        allowed = self.settings.media_allowed_host_set
        return host in allowed or any(host.endswith(f".{allowed_host}") for allowed_host in allowed)

    def _fetch_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Referer": self.settings.media_referer,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }

    def probe_cover_url(self, url: str) -> bool:
        if not self.is_allowed_media_url(url):
            return False
        try:
            with httpx.Client(timeout=self.settings.media_fetch_timeout_seconds, follow_redirects=True) as client:
                response = client.head(url, headers=self._fetch_headers())
                if response.status_code == 405:
                    response = client.get(url, headers=self._fetch_headers())
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def download_cover(self, url: str) -> tuple[bytes, str] | None:
        if not self.is_allowed_media_url(url):
            return None
        try:
            with httpx.Client(timeout=self.settings.media_fetch_timeout_seconds, follow_redirects=True) as client:
                response = client.get(url, headers=self._fetch_headers())
                if response.status_code != 200:
                    return None
                content_type = (response.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
                return response.content, content_type
        except httpx.HTTPError:
            return None

    def extension_for_content_type(self, content_type: str) -> str:
        return _CONTENT_TYPE_EXT.get(content_type.lower(), "jpg")

    def persist_cover(self, content_id: str, data: bytes, content_type: str) -> str:
        ext = self.extension_for_content_type(content_type)
        relative = f"{content_id}/cover.{ext}"
        target = self.media_root() / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return relative

    def resolve_local_cover_path(self, stored_cover_path: str | None) -> Path | None:
        if not stored_cover_path:
            return None
        relative = Path(stored_cover_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        candidate = (self.media_root() / relative).resolve()
        if not str(candidate).startswith(str(self.media_root())):
            return None
        return candidate if candidate.is_file() else None

    def resolve_after_detail_ingest(self, snapshot: ContentSnapshot) -> None:
        cover_url = (snapshot.cover_url or "").strip()
        if not cover_url:
            snapshot.cover_media_status = COVER_MEDIA_UNAVAILABLE
            snapshot.stored_cover_path = None
            return
        if not self.is_allowed_media_url(cover_url):
            snapshot.cover_media_status = COVER_MEDIA_UNAVAILABLE
            snapshot.stored_cover_path = None
            return
        if self.probe_cover_url(cover_url):
            snapshot.cover_media_status = COVER_MEDIA_PROXY_OK
            snapshot.stored_cover_path = None
            return
        downloaded = self.download_cover(cover_url)
        if downloaded:
            data, content_type = downloaded
            snapshot.stored_cover_path = self.persist_cover(snapshot.content_id, data, content_type)
            snapshot.cover_media_status = COVER_MEDIA_STORED
            return
        snapshot.cover_media_status = COVER_MEDIA_UNAVAILABLE
        snapshot.stored_cover_path = None

    def sign_cover_token(self, content_id: str, expires_at: int | None = None) -> tuple[int, str]:
        expires = expires_at or int(time.time()) + self.settings.media_url_ttl_seconds
        payload = f"{content_id}:{expires}"
        signature = hmac.new(
            self.settings.media_signing_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return expires, signature

    def verify_cover_token(self, content_id: str, expires_at: int, signature: str) -> bool:
        if expires_at < int(time.time()):
            return False
        expected = hmac.new(
            self.settings.media_signing_key.encode("utf-8"),
            f"{content_id}:{expires_at}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def build_cover_display_url_for_snapshot(
        self,
        content_id: str,
        snapshot: ContentSnapshot | None,
        metadata: dict | None = None,
    ) -> str | None:
        metadata = metadata or {}
        cover_url = snapshot.cover_url if snapshot else metadata.get("cover_url")
        stored_cover_path = snapshot.stored_cover_path if snapshot else None
        return self.build_cover_display_url(
            content_id,
            stored_cover_path=stored_cover_path,
            cover_url=cover_url if cover_url else None,
        )

    def build_cover_display_url(
        self,
        content_id: str,
        *,
        stored_cover_path: str | None = None,
        cover_url: str | None = None,
    ) -> str | None:
        if not stored_cover_path and not (cover_url and str(cover_url).strip()):
            return None
        if cover_url and not stored_cover_path and not self.is_allowed_media_url(cover_url):
            return None
        expires, signature = self.sign_cover_token(content_id)
        return f"/api/media/cover/{content_id}?e={expires}&s={signature}"

    def fetch_remote_cover(self, url: str) -> tuple[bytes, str] | None:
        return self.download_cover(url)

    def guess_media_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".webp":
            return "image/webp"
        if suffix == ".png":
            return "image/png"
        if suffix == ".gif":
            return "image/gif"
        return "image/jpeg"
