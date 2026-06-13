import asyncio

from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe


def test_search_probe_accepts_xhs_filter_context():
    probe = XhsSearchProbe(
        keywords=["SCI"],
        max_items=10,
        search_sort="most_liked",
        note_type="image_text",
        publish_time="half_year",
        search_scope="followed",
        location_filter="nearby",
        start_rank=5,
    )
    assert probe.search_sort == "most_liked"
    assert probe.location_filter == "nearby"
    assert probe.start_rank == 5
    assert probe.apply_filters is True


class _FakeMouse:
    async def wheel(self, dx, dy):
        return None


class _FakePage:
    """Minimal page returning a fixed set of search cards on every evaluate."""

    def __init__(self, cards):
        self._cards = cards
        self.mouse = _FakeMouse()

    async def goto(self, url, **kwargs):
        return None

    async def wait_for_timeout(self, ms):
        return None

    async def evaluate(self, script):
        return list(self._cards)


def test_search_probe_start_rank_slices_results():
    cards = [
        {"href": f"https://www.xiaohongshu.com/explore/note-{i}", "title": f"t{i}"}
        for i in range(8)
    ]
    probe = XhsSearchProbe(keywords=["SCI"], max_items=3, start_rank=2, apply_filters=False)
    candidates, report = asyncio.run(probe.collect(_FakePage(cards)))

    # start_rank=2 → skip first 2, take next 3 (note-2, note-3, note-4)
    assert [c.platform_content_id for c in candidates] == ["note-2", "note-3", "note-4"]
    assert report["start_rank"] == 2
    assert report["filter_apply_status"] == "not_applicable"


def test_search_card_exposes_filter_apply_status():
    from local_agent_runtime.connectors.xhs.normalizer import normalize_xhs_search_card

    candidate = normalize_xhs_search_card(
        {"href": "https://www.xiaohongshu.com/explore/note-x", "title": "SCI"},
        search_keyword="SCI",
        rank_position=1,
        search_sort="most_liked",
    )
    assert candidate.raw_payload["filter_apply_status"] == "not_implemented"
    assert candidate.raw_payload["requested_filter_context"]["search_sort"] == "most_liked"
