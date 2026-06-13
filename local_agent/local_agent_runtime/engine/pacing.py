"""Human-like pacing for browser collection.

Goal: make scrolling/dwelling look like a real person rather than a bot, so
platforms (XHS / Douyin / ...) are less likely to flag the session as
automated. The same controller drives every platform connector; only the page
primitives differ per platform.

Design notes:
- All timing decisions are pure (``plan_scroll`` / ``*_ms``) so they can be
  unit-tested deterministically with a seeded RNG, without a real browser.
- The async ``human_scroll`` / ``initial_dwell`` apply those decisions onto a
  Playwright ``Page`` using only ``mouse.wheel`` and ``wait_for_timeout`` so
  they work with the existing fake-page test doubles.
- ``BehaviorProfile`` is hydratable from a central ``BehaviorProfile`` payload
  via ``from_mapping`` so the central risk/behavior center can tune pacing per
  account without code changes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, fields
from typing import Any, Mapping, Protocol


class _PageLike(Protocol):
    @property
    def mouse(self) -> Any: ...

    async def wait_for_timeout(self, timeout: float) -> Any: ...


def _coerce_bounds(value: Any, fallback: tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = int(value[0]), int(value[1])
        if hi < lo:
            lo, hi = hi, lo
        return max(0, lo), max(0, hi)
    if isinstance(value, (int, float)):
        v = max(0, int(value))
        return v, v
    return fallback


@dataclass(frozen=True)
class BehaviorProfile:
    """Tunable ranges describing how a human browses a feed.

    All ``*_px`` / ``*_ms`` are inclusive ``(min, max)`` bounds; a value is
    sampled uniformly from the range each time it is used.
    """

    scroll_distance_px: tuple[int, int] = (700, 2100)
    scroll_pause_ms: tuple[int, int] = (650, 2400)
    initial_dwell_ms: tuple[int, int] = (900, 2200)
    # Occasionally pause longer, as if reading a card that caught the eye.
    reading_pause_probability: float = 0.18
    reading_pause_ms: tuple[int, int] = (1800, 4200)
    # Occasionally scroll back up a little, as if re-reading something.
    backscroll_probability: float = 0.12
    backscroll_px: tuple[int, int] = (180, 620)
    # Tiny pauses between micro-actions (e.g. before/after a back-scroll).
    micro_pause_ms: tuple[int, int] = (90, 320)
    # Delay between two jobs on the same account, to avoid machine-gun pacing.
    inter_job_delay_ms: tuple[int, int] = (3000, 12000)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "BehaviorProfile":
        """Build a profile from a (possibly partial) central payload.

        Unknown keys are ignored; missing keys fall back to defaults. Bounds
        may be given as ``[min, max]`` or a single number.
        """

        if not data:
            return cls()
        defaults = cls()
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            raw = data[f.name]
            if f.name.endswith("_probability"):
                try:
                    kwargs[f.name] = max(0.0, min(1.0, float(raw)))
                except (TypeError, ValueError):
                    pass
            else:
                kwargs[f.name] = _coerce_bounds(raw, getattr(defaults, f.name))
        return cls(**kwargs)


@dataclass(frozen=True)
class ScrollStep:
    """A single planned scroll action."""

    distance_px: int
    pause_ms: int
    back_px: int = 0
    reading_pause_ms: int = 0

    @property
    def total_wait_ms(self) -> int:
        return (self.reading_pause_ms or self.pause_ms) + (1 if self.back_px else 0)


class PacingController:
    """Drives human-like pacing onto a browser page.

    Pass a seeded ``random.Random`` for deterministic tests.
    """

    def __init__(self, profile: BehaviorProfile | None = None, *, rng: random.Random | None = None):
        self.profile = profile or BehaviorProfile()
        self._rng = rng or random.Random()

    def _between(self, bounds: tuple[int, int]) -> int:
        lo, hi = bounds
        lo, hi = int(lo), int(hi)
        if hi <= lo:
            return max(0, lo)
        return self._rng.randint(lo, hi)

    def plan_scroll(self) -> ScrollStep:
        distance = self._between(self.profile.scroll_distance_px)
        pause = self._between(self.profile.scroll_pause_ms)
        back = (
            self._between(self.profile.backscroll_px)
            if self._rng.random() < self.profile.backscroll_probability
            else 0
        )
        reading = (
            self._between(self.profile.reading_pause_ms)
            if self._rng.random() < self.profile.reading_pause_probability
            else 0
        )
        return ScrollStep(distance_px=distance, pause_ms=pause, back_px=back, reading_pause_ms=reading)

    def initial_dwell_ms(self) -> int:
        return self._between(self.profile.initial_dwell_ms)

    def inter_job_delay_ms(self) -> int:
        return self._between(self.profile.inter_job_delay_ms)

    async def human_scroll(self, page: _PageLike) -> ScrollStep:
        """Scroll down by a randomized amount with a randomized dwell.

        Occasionally inserts a longer "reading" pause and/or a small
        back-scroll to better resemble human browsing.
        """

        step = self.plan_scroll()
        await page.mouse.wheel(0, step.distance_px)
        await page.wait_for_timeout(step.reading_pause_ms or step.pause_ms)
        if step.back_px:
            await page.wait_for_timeout(self._between(self.profile.micro_pause_ms))
            await page.mouse.wheel(0, -step.back_px)
            await page.wait_for_timeout(self._between(self.profile.micro_pause_ms))
        return step

    async def initial_dwell(self, page: _PageLike) -> int:
        """Pause after landing on a page, as a human would orient first."""

        ms = self.initial_dwell_ms()
        await page.wait_for_timeout(ms)
        return ms
