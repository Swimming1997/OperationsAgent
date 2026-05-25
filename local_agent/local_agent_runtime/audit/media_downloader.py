from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass(frozen=True)
class DownloadedMedia:
    index: int
    source_url: str
    local_path: str
    bytes: int | None
    status: str
    error: str | None = None


def guess_media_extension(*, url: str, content_type: str | None) -> str:
    if content_type:
        normalized = content_type.split(";")[0].strip().lower()
        if normalized in CONTENT_TYPE_EXTENSIONS:
            return CONTENT_TYPE_EXTENSIONS[normalized]
    path = urlparse(url).path.lower()
    for ext in (".webp", ".png", ".gif", ".jpeg", ".jpg"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


async def download_media_files(
    urls: list[str],
    output_dir: Path,
    *,
    prefix: str = "image",
    max_count: int = 20,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
    relative_to: Path | None = None,
) -> list[DownloadedMedia]:
    output_dir.mkdir(parents=True, exist_ok=True)
    relative_to = relative_to or output_dir.parent
    results: list[DownloadedMedia] = []
    close_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        for index, source_url in enumerate(urls[:max_count], start=1):
            if not source_url:
                results.append(
                    DownloadedMedia(
                        index=index,
                        source_url=str(source_url),
                        local_path="",
                        bytes=None,
                        status="failed",
                        error="empty_url",
                    )
                )
                continue
            try:
                response = await http_client.get(source_url)
                response.raise_for_status()
                ext = guess_media_extension(url=source_url, content_type=response.headers.get("content-type"))
                filename = f"{prefix}_{index:02d}{ext}"
                target = output_dir / filename
                content = response.content
                target.write_bytes(content)
                relative_path = target.relative_to(relative_to).as_posix()
                results.append(
                    DownloadedMedia(
                        index=index,
                        source_url=source_url,
                        local_path=relative_path,
                        bytes=len(content),
                        status="ok",
                    )
                )
            except Exception as exc:
                results.append(
                    DownloadedMedia(
                        index=index,
                        source_url=source_url,
                        local_path="",
                        bytes=None,
                        status="failed",
                        error=str(exc)[:300],
                    )
                )
    finally:
        if close_client:
            await http_client.aclose()
    write_media_manifest(output_dir, files=results)
    return results


def write_media_manifest(output_dir: Path, *, files: list[DownloadedMedia], extra: dict[str, Any] | None = None) -> Path:
    payload = {"files": [asdict(item) for item in files]}
    if extra:
        payload.update(extra)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
