from __future__ import annotations

import random


class IdlePollBackoff:
    """Adaptive claim delay with jitter to avoid synchronized Agent polling."""

    def __init__(
        self,
        *,
        minimum_seconds: float,
        maximum_seconds: float,
        multiplier: float = 1.8,
        jitter_ratio: float = 0.2,
        rng: random.Random | None = None,
    ):
        self.minimum_seconds = max(0.01, float(minimum_seconds))
        self.maximum_seconds = max(self.minimum_seconds, float(maximum_seconds))
        self.multiplier = max(1.0, float(multiplier))
        self.jitter_ratio = max(0.0, min(0.9, float(jitter_ratio)))
        self._rng = rng or random.Random()
        self._base_delay = self.minimum_seconds

    def next_delay(self, *, handled_count: int, request_failed: bool = False) -> float:
        if handled_count > 0:
            self._base_delay = self.minimum_seconds
        elif request_failed:
            self._base_delay = min(self.maximum_seconds, self._base_delay * max(2.0, self.multiplier))
        else:
            current = self._base_delay
            self._base_delay = min(self.maximum_seconds, self._base_delay * self.multiplier)
            return self._with_jitter(current)
        return self._with_jitter(self._base_delay)

    def _with_jitter(self, seconds: float) -> float:
        spread = seconds * self.jitter_ratio
        if spread <= 0:
            return seconds
        return min(
            self.maximum_seconds,
            max(0.01, self._rng.uniform(seconds - spread, seconds + spread)),
        )
