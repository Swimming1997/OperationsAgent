import asyncio
import json

from local_agent_runtime.connectors.douyin.creator_probe import (
    DouyinCreatorProbe,
    parse_douyin_creator_id,
)


class FakeResponse:
    url = "https://www.douyin.com/aweme/v1/web/aweme/post/"

    async def text(self):
        return json.dumps(
            {
                "aweme_list": [
                    {
                        "aweme_id": "aweme-1",
                        "desc": "作品",
                        "author": {
                            "sec_uid": "sec-1",
                            "nickname": "作者",
                            "follower_count": 100,
                            "aweme_count": 10,
                        },
                        "statistics": {"digg_count": 9},
                        "video": {"cover": {"url_list": ["https://img.test/c.jpg"]}},
                    }
                ]
            }
        )


class FakeMouse:
    async def wheel(self, dx, dy):
        return None


class FakePage:
    def __init__(self):
        self.listeners = []
        self.mouse = FakeMouse()

    def on(self, event, callback):
        self.listeners.append(callback)

    def remove_listener(self, event, callback):
        self.listeners.remove(callback)

    async def goto(self, url, **kwargs):
        for callback in list(self.listeners):
            callback(FakeResponse())

    async def wait_for_timeout(self, ms):
        return None


def test_parse_douyin_creator_id_accepts_id_and_profile_url():
    assert parse_douyin_creator_id("sec-1") == "sec-1"
    assert parse_douyin_creator_id("https://www.douyin.com/user/sec-1") == "sec-1"


def test_creator_probe_captures_posts_and_profile():
    result = asyncio.run(
        DouyinCreatorProbe(max_scrolls=0).fetch_latest(
            FakePage(),
            creator_platform_id="sec-1",
            limit=10,
        )
    )
    assert result.creator_platform_id == "sec-1"
    assert result.creator_display_name == "作者"
    assert [item.platform_content_id for item in result.items] == ["aweme-1"]
    assert result.items[0].author_platform_id == "sec-1"
    assert result.profile["follower_count"] == 100
