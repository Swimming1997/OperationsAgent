from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


class PerfTimer:
    def __init__(self) -> None:
        self._started = time.perf_counter()
        self._marks: dict[str, float] = {}
        self._durations: dict[str, float] = {}
        self._items = 0

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._durations[f"{name}_ms"] = round((time.perf_counter() - start) * 1000, 2)

    def mark(self, name: str) -> None:
        self._marks[f"{name}_ms"] = round((time.perf_counter() - self._started) * 1000, 2)

    def set_items(self, count: int) -> None:
        self._items = max(0, count)

    def summary(self) -> dict[str, float]:
        total_ms = round((time.perf_counter() - self._started) * 1000, 2)
        result: dict[str, float] = {
            "session_acquire_ms": 0.0,
            "page_goto_ms": 0.0,
            "initial_wait_ms": 0.0,
            "scroll_ms": 0.0,
            "api_ms": 0.0,
            "network_capture_ms": 0.0,
            "dom_extract_ms": 0.0,
            "normalize_ms": 0.0,
            "ingestion_ms": 0.0,
            **self._marks,
            **self._durations,
            "total_ms": total_ms,
            "items_per_second": round(self._items / (total_ms / 1000), 3) if total_ms > 0 and self._items else 0.0,
        }
        return result


SURFACE_STAGE_KEYS = (
    "session_acquire_ms",
    "page_goto_ms",
    "initial_wait_ms",
    "scroll_ms",
    "api_ms",
    "network_capture_ms",
    "dom_extract_ms",
    "normalize_ms",
    "ingestion_ms",
)


def merge_surface_perf(timer: PerfTimer, probe_perf: dict[str, Any] | None, *, item_count: int) -> dict[str, float]:
    """Keep wall-clock total_ms from timer; merge stage breakdown from probe without inflating totals."""
    perf = timer.summary()
    probe_perf = probe_perf or {}
    for key in SURFACE_STAGE_KEYS:
        if key in probe_perf:
            perf[key] = float(probe_perf[key])
    total_ms = float(perf.get("total_ms") or 0.0)
    perf["items_per_second"] = round(item_count / (total_ms / 1000), 3) if total_ms > 0 and item_count else 0.0
    return perf

