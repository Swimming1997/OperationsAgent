"""Platform-agnostic search query configuration.

Upper-layer applications configure search/long-tail collection once using a
single vocabulary; each connector translates these canonical values into the
platform's native filters (URL params or filter-panel clicks). Keeping the
vocabulary here (not inside a connector) is what lets XHS and Douyin look the
same to the central server and the operator UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SORT_VALUES = ("comprehensive", "latest", "most_liked", "most_commented", "most_collected")
CONTENT_FORM_VALUES = ("all", "video", "image_text")
PUBLISH_TIME_VALUES = ("all", "one_day", "one_week", "half_year")
DURATION_VALUES = ("all", "under_1m", "1m_to_5m", "over_5m")

# Legacy XHS payload keys → canonical keys, so existing central jobs keep working.
_LEGACY_ALIASES = {
    "search_sort": "sort",
    "note_type": "content_form",
}


def _coerce(value: object, allowed: tuple[str, ...], default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text in allowed else default


@dataclass(frozen=True)
class SearchQueryConfig:
    keywords: list[str] = field(default_factory=list)
    sort: str = "comprehensive"
    content_form: str = "all"
    publish_time: str = "all"
    duration: str = "all"
    max_items: int = 40
    start_rank: int = 0

    @classmethod
    def from_payload(cls, payload: dict | None) -> "SearchQueryConfig":
        data = dict(payload or {})
        for legacy, canonical in _LEGACY_ALIASES.items():
            if canonical not in data and legacy in data:
                data[canonical] = data[legacy]

        raw_keywords = data.get("keywords")
        if not raw_keywords and data.get("keyword"):
            raw_keywords = [data["keyword"]]
        keywords = [str(k).strip() for k in (raw_keywords or []) if str(k).strip()]

        try:
            max_items = max(1, int(data.get("max_items") or 40))
        except (TypeError, ValueError):
            max_items = 40
        try:
            start_rank = max(0, int(data.get("start_rank") or 0))
        except (TypeError, ValueError):
            start_rank = 0

        return cls(
            keywords=keywords,
            sort=_coerce(data.get("sort"), SORT_VALUES, "comprehensive"),
            content_form=_coerce(data.get("content_form"), CONTENT_FORM_VALUES, "all"),
            publish_time=_coerce(data.get("publish_time"), PUBLISH_TIME_VALUES, "all"),
            duration=_coerce(data.get("duration"), DURATION_VALUES, "all"),
            max_items=max_items,
            start_rank=start_rank,
        )

    def has_non_default_filters(self) -> bool:
        return (
            self.sort != "comprehensive"
            or self.content_form != "all"
            or self.publish_time != "all"
            or self.duration != "all"
        )

    def requested_filter_context(self) -> dict[str, str]:
        return {
            "sort": self.sort,
            "content_form": self.content_form,
            "publish_time": self.publish_time,
            "duration": self.duration,
        }
