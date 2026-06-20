import asyncio
import inspect

from local_agent_runtime.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from local_agent_runtime.connectors.xhs.response_capture import classify_xhs_api_surface
from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe


class FakeResponse:
    def __init__(self, url, payload):
        self.url = url
        self._payload = payload

    async def json(self):
        return self._payload


class FakeMouse:
    async def wheel(self, dx, dy):
        return None


class FakePage:
    def __init__(self, response):
        self.url = "about:blank"
        self.mouse = FakeMouse()
        self._response = response
        self._listeners = []

    def on(self, event, callback):
        if event == "response":
            self._listeners.append(callback)

    async def goto(self, url, **kwargs):
        self.url = url
        for callback in self._listeners:
            result = callback(self._response)
            if inspect.isawaitable(result):
                await result

    async def wait_for_timeout(self, ms):
        return None

    async def evaluate(self, script):
        raise AssertionError("DOM fallback should not run when API reaches target")


def api_item(note_id):
    return {
        "id": note_id,
        "xsec_token": f"token-{note_id}",
        "xsec_source": "pc_search",
        "note_card": {
            "display_title": f"title-{note_id}",
            "user": {"user_id": "user-1", "nickname": "作者"},
            "interact_info": {"liked_count": "123"},
            "cover": {"url_default": "https://img.test/cover.jpg"},
        },
    }


def test_classifies_xhs_feed_and_search_responses():
    assert classify_xhs_api_surface("https://edith.xiaohongshu.com/api/sns/web/v1/search/notes") == "search"
    assert classify_xhs_api_surface("https://edith.xiaohongshu.com/api/sns/web/v1/homefeed") == "homefeed"
    assert classify_xhs_api_surface("https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo") is None


def test_search_probe_prefers_captured_api_response():
    page = FakePage(
        FakeResponse(
            "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
            {"data": {"items": [api_item("note-1"), api_item("note-2")]}},
        )
    )
    candidates, report = asyncio.run(
        XhsSearchProbe(
            keywords=["SCI"],
            max_items=2,
            max_scrolls_per_keyword=0,
            apply_filters=False,
        ).collect(page)
    )

    assert [item.platform_content_id for item in candidates] == ["note-1", "note-2"]
    assert report["source_path"] == "api_response_capture"
    assert report["api_cards_seen"] == 2
    assert report["dom_fallback_used"] is False


def test_homefeed_probe_prefers_captured_api_response():
    item = api_item("feed-1")
    item["xsec_source"] = "pc_feed"
    page = FakePage(
        FakeResponse(
            "https://edith.xiaohongshu.com/api/sns/web/v1/homefeed",
            {"data": {"items": [item]}},
        )
    )
    candidates, report = asyncio.run(
        XhsHomeFeedProbe(target_count=1, max_scrolls=0).collect(page)
    )

    assert [item.platform_content_id for item in candidates] == ["feed-1"]
    assert report["source_path"] == "api_response_capture"
    assert report["api_payload_count"] == 1
