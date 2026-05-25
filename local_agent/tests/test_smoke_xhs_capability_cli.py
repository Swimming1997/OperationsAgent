from __future__ import annotations

import importlib.util
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from local_agent_runtime.smoke.contract import validate_smoke_report
from local_agent_runtime.smoke.output import render_smoke_markdown, write_smoke_outputs
from local_agent_runtime.smoke.runner import SmokeRunOptions, XhsCapabilitySmokeRunner


def _load_smoke_cli_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_xhs_capability.py"
    spec = importlib.util.spec_from_file_location("smoke_xhs_capability", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_parser_accepts_capabilities():
    module = _load_smoke_cli_module()
    parser = module.build_parser()
    args = parser.parse_args(["--capability", "homefeed", "--profile-key", "collector_01", "--max-items", "10"])
    assert args.capability == "homefeed"
    assert args.profile_key == "collector_01"
    assert args.max_items == 10
    assert module.parse_bool("false") is False
    assert module.parse_bool("true") is True


def test_smoke_output_json_structure(tmp_path: Path):
    report = {
        "run_id": "abc123",
        "capability": "search_collect",
        "profile_key": "collector_01",
        "started_at": "2026-05-24T00:00:00+00:00",
        "finished_at": "2026-05-24T00:00:01+00:00",
        "status": "partial",
        "error_code": None,
        "error_message": None,
        "timings_ms": {
            "browser_acquire": 1,
            "page_goto": 2,
            "initial_wait": 3,
            "filter_apply": 4,
            "scroll": 5,
            "dom_extract": 6,
            "normalize": 0,
            "total": 21,
        },
        "requested_filter_context": {"search_sort": "most_liked", "note_type": "all", "publish_time": "all"},
        "applied_filter_context": None,
        "filter_apply_status": "not_implemented",
        "item_count": 2,
        "items": [
            {
                "platform": "xhs",
                "platform_content_id": "note-1",
                "canonical_url": "https://www.xiaohongshu.com/explore/note-1",
                "title": "SCI",
                "search_rank": 1,
                "search_keyword": "医学sci求助",
            }
        ],
        "diagnostics": {"current_url": "https://www.xiaohongshu.com/search_result", "page_title": "search"},
    }
    paths = write_smoke_outputs(report, tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["capability"] == "search_collect"
    assert payload["timings_ms"]["total"] == 21
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "XHS Capability Smoke Report" in markdown
    assert "not_implemented" in markdown


def test_runner_failed_has_error_code(tmp_path: Path):
    options = SmokeRunOptions(
        capability="detail",
        profile_key="collector_01",
        project_root=tmp_path,
        output_dir=tmp_path,
    )

    async def _run():
        with patch.object(XhsCapabilitySmokeRunner, "_acquire_page", AsyncMock(return_value=None)):
            with patch.object(XhsCapabilitySmokeRunner, "_close_session", AsyncMock()):
                return await XhsCapabilitySmokeRunner(options).run()

    report = asyncio.run(_run())
    assert report["status"] == "failed"
    assert report["error_code"] is not None


def test_runner_search_collect_mock_items(tmp_path: Path):
    from local_agent_runtime.contracts import FeedCandidateInput
    from local_agent_runtime.enums import ContentType, Platform, SourceSurface
    from datetime import datetime, timezone

    candidate = FeedCandidateInput(
        platform=Platform.XHS,
        platform_content_id="note-abc",
        canonical_url="https://www.xiaohongshu.com/explore/note-abc",
        content_type=ContentType.IMAGE_TEXT,
        title_or_summary="SCI论文",
        source_surface=SourceSurface.SEARCH,
        discovered_at=datetime.now(timezone.utc),
        raw_payload={"search_keyword": "医学sci求助", "search_rank": 1},
    )
    fake_page = AsyncMock()
    fake_page.url = "https://www.xiaohongshu.com/search_result"
    fake_page.goto = AsyncMock()
    fake_page.wait_for_timeout = AsyncMock()
    options = SmokeRunOptions(
        capability="search_collect",
        profile_key="collector_01",
        project_root=tmp_path,
        output_dir=tmp_path,
        keyword="医学sci求助",
        max_items=5,
    )

    async def _run():
        async def fake_acquire(self, state):
            return fake_page

        async def fake_capture(self, page, state, *, base_name):
            return None

        with patch.object(XhsCapabilitySmokeRunner, "_acquire_page", fake_acquire):
            with patch.object(XhsCapabilitySmokeRunner, "_close_session", AsyncMock()):
                with patch.object(XhsCapabilitySmokeRunner, "_capture_artifacts", fake_capture):
                    with patch("local_agent_runtime.smoke.runner.apply_search_filters", AsyncMock(return_value=(None, "not_implemented", {}, 0.0))):
                        with patch("local_agent_runtime.smoke.runner.XhsSearchProbe") as probe_cls:
                            probe = probe_cls.return_value
                            probe.collect = AsyncMock(return_value=([candidate], {"perf": {}}))
                            return await XhsCapabilitySmokeRunner(options).run()

    report = asyncio.run(_run())
    assert report["item_count"] == 1
    assert report["items"][0]["search_keyword"] == "医学sci求助"
    assert report["filter_apply_status"] == "not_applicable"
