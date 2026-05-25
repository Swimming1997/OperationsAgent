import pytest

from local_agent_runtime.audit.media_downloader import guess_media_extension


def test_guess_media_extension_defaults_to_jpg():
    assert guess_media_extension(url="https://example.com/noext", content_type=None) == ".jpg"


def test_guess_media_extension_handles_gif():
    assert guess_media_extension(url="https://example.com/x", content_type="image/gif") == ".gif"
