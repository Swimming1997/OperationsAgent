from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class XhsApiPayload:
    url: str
    surface: str
    data: dict[str, Any]


def classify_xhs_api_surface(url: str) -> str | None:
    normalized = str(url or "").lower()
    if "/api/sns/web/v1/search/notes" in normalized:
        return "search"
    if any(
        marker in normalized
        for marker in (
            "/api/sns/web/v1/homefeed",
            "/api/sns/web/v1/feed",
            "/api/sns/web/v1/recommend",
        )
    ):
        return "homefeed"
    return None


class XhsResponseCapture:
    """Capture JSON returned to the logged-in XHS page without issuing extra requests."""

    def __init__(self) -> None:
        self._payloads: list[XhsApiPayload] = []
        self._pending: set[asyncio.Task[Any]] = set()
        self.attached = False

    def attach(self, page: Any) -> bool:
        on = getattr(page, "on", None)
        if not callable(on):
            return False
        on("response", self._schedule_response)
        self.attached = True
        return True

    def _schedule_response(self, response: Any) -> None:
        task = asyncio.create_task(self._capture_response(response))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _capture_response(self, response: Any) -> None:
        url = str(getattr(response, "url", "") or "")
        surface = classify_xhs_api_surface(url)
        if surface is None:
            return
        try:
            payload = await response.json()
        except Exception:
            return
        data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
        if isinstance(data, dict):
            self._payloads.append(XhsApiPayload(url=url, surface=surface, data=data))

    async def drain(self, surface: str) -> list[XhsApiPayload]:
        if self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)
        matched = [item for item in self._payloads if item.surface == surface]
        self._payloads = [item for item in self._payloads if item.surface != surface]
        return matched

