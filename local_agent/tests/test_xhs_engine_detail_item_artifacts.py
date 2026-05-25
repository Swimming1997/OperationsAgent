import asyncio
import json
from pathlib import Path

import httpx

from local_agent_runtime.audit.logger import (
    EngineAuditLogger,
    build_detail_item_markdown,
    serialize_detail_item,
)
from local_agent_runtime.audit.media_downloader import download_media_files, guess_media_extension


def test_download_media_files_writes_file(tmp_path: Path):
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "Cookie" not in request.headers
            return httpx.Response(200, content=b"fake-image-bytes", headers={"content-type": "image/jpeg"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            results = await download_media_files(
                ["https://example.com/a.jpg"],
                tmp_path / "media" / "detail_note001",
                client=client,
                relative_to=tmp_path,
            )
        assert len(results) == 1
        assert results[0].status == "ok"
        assert results[0].bytes == len(b"fake-image-bytes")
        assert results[0].local_path == "media/detail_note001/image_01.jpg"
        assert (tmp_path / results[0].local_path).exists()
        manifest = json.loads((tmp_path / "media" / "detail_note001" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["files"][0]["status"] == "ok"

    asyncio.run(run())


def test_download_media_files_records_failure_without_crashing(tmp_path: Path):
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, content=b"not found")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            results = await download_media_files(
                ["https://example.com/missing.jpg"],
                tmp_path / "media" / "detail_note002",
                client=client,
                relative_to=tmp_path,
            )
        assert results[0].status == "failed"
        assert results[0].error

    asyncio.run(run())


def test_guess_media_extension_from_content_type_and_url():
    assert guess_media_extension(url="https://x.test/a", content_type="image/webp") == ".webp"
    assert guess_media_extension(url="https://x.test/a.png", content_type=None) == ".png"


def test_serialize_detail_item_includes_full_body_text_and_image_urls():
    item = serialize_detail_item(
        note_id="note001",
        url="https://www.xiaohongshu.com/explore/note001",
        snapshot={
            "title": "标题",
            "author_name": "作者",
            "author_platform_id": "uid001",
            "body_text": "完整正文" * 100,
            "image_urls": ["https://img.example/1.jpg"],
            "like_count": 1,
            "comment_count": 2,
            "collect_count": 3,
            "share_count": 4,
        },
        diagnostics={"fetch_source": "api", "api_success": True, "canonical_url": "https://x.test/u"},
    )
    assert len(item["body_text"]) > 300
    assert "body_text_preview" not in item
    assert item["image_urls"] == ["https://img.example/1.jpg"]


def test_detail_item_markdown_contains_body_text_and_image_table(tmp_path: Path):
    item = serialize_detail_item(
        note_id="note001",
        url="https://www.xiaohongshu.com/explore/note001",
        snapshot={
            "title": "标题",
            "author_name": "作者",
            "body_text": "完整正文内容",
            "image_urls": ["https://img.example/1.jpg"],
        },
        diagnostics={"fetch_source": "api", "api_success": True},
        downloaded_images=[
            {
                "index": 1,
                "source_url": "https://img.example/1.jpg",
                "local_path": "media/detail_note001/image_01.jpg",
                "bytes": 123,
                "status": "ok",
            }
        ],
    )
    md = build_detail_item_markdown("run001", item)
    assert "## body_text" in md
    assert "完整正文内容" in md
    assert "## image_urls" in md
    assert "media/detail_note001/image_01.jpg" in md
    assert "![image_01.jpg](media/detail_note001/image_01.jpg)" in md

    logger = EngineAuditLogger(project_root=tmp_path, run_id="20260524_test001")
    artifacts = logger.write_detail_item(item)
    json_payload = json.loads((logger.output_dir / artifacts["detail_item_json"]).read_text(encoding="utf-8"))
    md_text = (logger.output_dir / artifacts["detail_item_md"]).read_text(encoding="utf-8")
    assert json_payload["body_text"] == "完整正文内容"
    assert artifacts["detail_media_dir"] == "media/detail_note001/"
    assert "Cookie" not in json.dumps(json_payload, ensure_ascii=False)
    assert "X-S" not in md_text
