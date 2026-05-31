from __future__ import annotations

import base64

import httpx
from playwright.async_api import Page

from local_agent_runtime.connectors.xhs.api_client import browser_context_cookie_header
from local_agent_runtime.contracts import DetailSnapshotInput

_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Referer": "https://www.xiaohongshu.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _pick_cover_url(snapshot: DetailSnapshotInput) -> str | None:
    cover_url = (snapshot.cover_url or "").strip()
    if cover_url and not cover_url.startswith(("blob:", "data:")):
        return cover_url
    for url in snapshot.image_urls:
        candidate = str(url or "").strip()
        if candidate and not candidate.startswith(("blob:", "data:")):
            return candidate
    return None


async def attach_cover_bytes(page: Page, snapshot: DetailSnapshotInput) -> DetailSnapshotInput:
    if snapshot.cover_image_base64:
        return snapshot
    cover_url = _pick_cover_url(snapshot)
    if not cover_url:
        return snapshot
    try:
        cookie_str = await browser_context_cookie_header(page.context)
        headers = {**_FETCH_HEADERS, "Cookie": cookie_str}
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(cover_url, headers=headers)
            if response.status_code != 200 or not response.content:
                return snapshot
            content_type = (response.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
            return snapshot.model_copy(
                update={
                    "cover_image_base64": base64.b64encode(response.content).decode("ascii"),
                    "cover_content_type": content_type,
                }
            )
    except Exception:
        return snapshot
