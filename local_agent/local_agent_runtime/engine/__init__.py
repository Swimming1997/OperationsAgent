"""Platform-agnostic collection engine core.

This package holds primitives that are shared across platform connectors
(XHS, Douyin, ...). Anti-detection behavior — randomized human-like pacing,
session lifecycle, risk pacing — lives here so it is implemented once and
driven uniformly, instead of being duplicated inside each connector.
"""

from local_agent_runtime.engine.pacing import (
    BehaviorProfile,
    PacingController,
    ScrollStep,
)
from local_agent_runtime.engine.search_config import SearchQueryConfig

__all__ = [
    "BehaviorProfile",
    "PacingController",
    "ScrollStep",
    "SearchQueryConfig",
]
