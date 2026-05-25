from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from local_agent_runtime.chrome_launcher import resolve_profile_dir
from local_agent_runtime.connectors.xhs.api_client import XhsApiClient, browser_context_cookie_header, extract_self_info_result
from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe
from local_agent_runtime.connectors.xhs.context import context_from_url_and_raw, merge_xhs_context, parse_xhs_note_context
from local_agent_runtime.connectors.xhs.creator import XhsCreatorConnector, parse_xhs_creator_context
from local_agent_runtime.connectors.xhs.detail_probe import XhsDetailProbe
from local_agent_runtime.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from local_agent_runtime.connectors.xhs.normalizer import build_search_filter_context
from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe
from local_agent_runtime.connectors.xhs.search_suggest_probe import XhsSearchSuggestProbe
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import SessionStatus
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider, evaluate_xhs_session_state
from local_agent_runtime.smoke import errors as smoke_errors
from local_agent_runtime.smoke.output import utc_now_iso, write_smoke_outputs
from local_agent_runtime.smoke.search_filter_applicator import apply_search_filters, filters_are_default


CAPABILITIES = {
    "login_check",
    "homefeed",
    "search_suggest",
    "search_collect",
    "detail",
    "comments",
    "creator_notes",
}


@dataclass
class SmokeRunOptions:
    capability: str
    profile_key: str
    project_root: Path
    keyword: str | None = None
    note_url: str | None = None
    creator_url: str | None = None
    max_items: int = 20
    search_sort: str = "comprehensive"
    note_type: str = "all"
    publish_time: str = "all"
    headless: bool = False
    save_html: bool = False
    save_screenshot: bool = False
    cdp_url: str | None = None
    output_dir: Path | None = None


@dataclass
class _RunState:
    timings_ms: dict[str, float] = field(default_factory=lambda: {
        "browser_acquire": 0.0,
        "page_goto": 0.0,
        "initial_wait": 0.0,
        "filter_apply": 0.0,
        "scroll": 0.0,
        "dom_extract": 0.0,
        "normalize": 0.0,
        "total": 0.0,
    })
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _default_output_dir(project_root: Path) -> Path:
    day = datetime.now().strftime("%Y%m%d")
    return project_root / "logs" / "smoke" / "xhs" / day


def _feed_item(candidate: FeedCandidateInput, *, rank_field: str, rank_value: int) -> dict[str, Any]:
    raw = dict(candidate.raw_payload or {})
    requested = raw.get("requested_filter_context") or {}
    return {
        "platform": "xhs",
        "platform_content_id": candidate.platform_content_id,
        "canonical_url": candidate.canonical_url,
        "title": candidate.title_or_summary,
        "cover_url": candidate.cover_url,
        "author_name": candidate.author_name,
        "visible_like_count": candidate.visible_like_count,
        rank_field: rank_value,
        "search_keyword": raw.get("search_keyword"),
        "requested_filter_context": requested,
        "applied_filter_context": raw.get("applied_filter_context"),
        "filter_apply_status": raw.get("filter_apply_status"),
        "raw_payload": raw,
    }


def _count_missing(items: list[dict[str, Any]], fields: list[str]) -> dict[str, int]:
    counts = {field: 0 for field in fields}
    for item in items:
        for field in fields:
            value = item.get(field)
            if value in (None, "", [], {}):
                counts[field] += 1
    return {field: count for field, count in counts.items() if count}


def _resolve_status(*, capability: str, item_count: int, error_code: str | None, partial: bool = False) -> str:
    if error_code:
        return "failed"
    if partial:
        return "partial"
    thresholds = {
        "login_check": 0,
        "homefeed": 10,
        "search_suggest": 5,
        "search_collect": 10,
        "detail": 0,
        "comments": 0,
        "creator_notes": 3,
    }
    minimum = thresholds.get(capability, 1)
    if capability == "login_check":
        return "success"
    if capability == "detail":
        return "success"
    if capability == "comments":
        return "success" if item_count >= 0 else "failed"
    if item_count >= minimum:
        return "success"
    if item_count > 0:
        return "partial"
    return "failed"


def _session_error_code(status: SessionStatus, message: str) -> str:
    lowered = (message or "").lower()
    if status == SessionStatus.EXPIRED or "login" in lowered:
        return smoke_errors.LOGIN_REQUIRED
    if "cdp" in lowered:
        return smoke_errors.CDP_CONNECT_FAILED
    if "profile" in lowered and "lock" in lowered:
        return smoke_errors.PROFILE_LOCKED
    if status == SessionStatus.UNAVAILABLE:
        return smoke_errors.BROWSER_START_FAILED
    return smoke_errors.UNKNOWN_ERROR


class XhsCapabilitySmokeRunner:
    def __init__(self, options: SmokeRunOptions):
        self.options = options
        self.run_id = _new_run_id()
        self.started_at = utc_now_iso()

    async def run(self) -> dict[str, Any]:
        total_started = time.perf_counter()
        state = _RunState()
        capability = self.options.capability
        if capability not in CAPABILITIES:
            return self._finalize_report(
                state,
                total_started,
                capability=capability,
                items=[],
                item_count=0,
                error_code=smoke_errors.UNKNOWN_ERROR,
                error_message=f"unsupported capability: {capability}",
            )

        handlers = {
            "login_check": self._run_login_check,
            "homefeed": self._run_homefeed,
            "search_suggest": self._run_search_suggest,
            "search_collect": self._run_search_collect,
            "detail": self._run_detail,
            "comments": self._run_comments,
            "creator_notes": self._run_creator_notes,
        }
        try:
            report = await handlers[capability](state)
        except Exception as exc:
            report = self._finalize_report(
                state,
                total_started,
                capability=capability,
                items=[],
                item_count=0,
                error_code=smoke_errors.UNKNOWN_ERROR,
                error_message=str(exc),
            )
        output_dir = self.options.output_dir or _default_output_dir(self.options.project_root)
        paths = write_smoke_outputs(report, output_dir)
        report["output_paths"] = paths
        return report

    async def _acquire_page(self, state: _RunState) -> Page | None:
        acquire_started = time.perf_counter()
        profile_dir = resolve_profile_dir(self.options.project_root, self.options.profile_key)
        session_meta: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": self.options.headless,
        }
        if self.options.cdp_url:
            session_meta = {"cdp_url": self.options.cdp_url, "probe_only": True, "headless": self.options.headless}
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        state.timings_ms["browser_acquire"] = round((time.perf_counter() - acquire_started) * 1000, 2)
        state.diagnostics["session_status"] = session.status.value if hasattr(session.status, "value") else str(session.status)
        state.diagnostics["session_message"] = session.message
        if session.status != SessionStatus.READY or not session.page:
            state.error_code = _session_error_code(session.status, session.message)
            state.error_message = session.message
            await session.close()
            return None
        self._session = session
        return session.page

    async def _capture_artifacts(self, page: Page | None, state: _RunState, *, base_name: str) -> None:
        if not page:
            return
        output_dir = self.options.output_dir or _default_output_dir(self.options.project_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            state.diagnostics["current_url"] = page.url
            state.diagnostics["page_title"] = await page.title()
        except Exception:
            pass
        if self.options.save_screenshot:
            screenshot_path = output_dir / f"{base_name}.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=False)
                state.diagnostics["screenshot_path"] = str(screenshot_path)
            except Exception as exc:
                state.diagnostics["screenshot_error"] = str(exc)
        if self.options.save_html:
            html_path = output_dir / f"{base_name}.html"
            try:
                content = await page.content()
                html_path.write_text(content, encoding="utf-8")
                state.diagnostics["html_path"] = str(html_path)
            except Exception as exc:
                state.diagnostics["html_error"] = str(exc)

    async def _close_session(self) -> None:
        session = getattr(self, "_session", None)
        if session:
            await session.close()

    def _finalize_report(
        self,
        state: _RunState,
        total_started: float,
        *,
        capability: str,
        items: list[Any],
        item_count: int | None = None,
        payload: dict[str, Any] | None = None,
        requested_filter_context: dict[str, Any] | None = None,
        applied_filter_context: dict[str, Any] | None = None,
        filter_apply_status: str = "not_applicable",
        status: str | None = None,
        partial: bool = False,
        error_code: str | None = None,
        error_message: str | None = None,
        missing_fields: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        state.timings_ms["total"] = round((time.perf_counter() - total_started) * 1000, 2)
        final_error_code = error_code or state.error_code
        final_error_message = error_message or state.error_message
        final_status = status or _resolve_status(
            capability=capability,
            item_count=item_count if item_count is not None else len(items),
            error_code=final_error_code,
            partial=partial,
        )
        return {
            "run_id": self.run_id,
            "capability": capability,
            "profile_key": self.options.profile_key,
            "started_at": self.started_at,
            "finished_at": utc_now_iso(),
            "status": final_status,
            "error_code": final_error_code,
            "error_message": final_error_message,
            "timings_ms": state.timings_ms,
            "requested_filter_context": requested_filter_context or {},
            "applied_filter_context": applied_filter_context,
            "filter_apply_status": filter_apply_status,
            "item_count": item_count if item_count is not None else len(items),
            "items": items,
            "payload": payload or {},
            "missing_fields": missing_fields or {},
            "diagnostics": state.diagnostics,
        }

    async def _run_login_check(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        page = await self._acquire_page(state)
        base_name = f"login_check_{self.run_id}"
        payload: dict[str, Any] = {}
        try:
            if not page:
                await self._capture_artifacts(page, state, base_name=base_name)
                login_status = "login_required" if state.error_code == smoke_errors.LOGIN_REQUIRED else "unknown"
                payload = {"login_status": login_status, "account_hint": "", "current_url": state.diagnostics.get("current_url", "")}
                return self._finalize_report(
                    state,
                    total_started,
                    capability="login_check",
                    items=[],
                    item_count=0,
                    payload=payload,
                    status="failed" if login_status != "valid" else "success",
                    error_code=state.error_code,
                    error_message=state.error_message,
                )

            visible_text = await page.locator("body").inner_text(timeout=5000)
            session_status, session_message = evaluate_xhs_session_state(url=page.url, visible_text=visible_text)
            login_status = "unknown"
            account_hint = ""
            if session_status == SessionStatus.READY:
                login_status = "valid"
            elif session_status == SessionStatus.EXPIRED:
                login_status = "login_required"
                state.error_code = smoke_errors.LOGIN_REQUIRED
                state.error_message = session_message
            else:
                login_status = "login_required"
                state.error_code = smoke_errors.LOGIN_REQUIRED
                state.error_message = session_message

            if login_status == "valid":
                try:
                    cookie_header = await browser_context_cookie_header(page.context)
                    client = XhsApiClient(cookie_str=cookie_header)
                    self_info = await client.query_self()
                    extract = extract_self_info_result(self_info if isinstance(self_info, dict) else {})
                    if extract.nickname or extract.user_id:
                        account_hint = extract.nickname or extract.user_id or extract.red_id or ""
                    else:
                        login_status = "login_required"
                        state.error_code = smoke_errors.LOGIN_REQUIRED
                        state.error_message = "self_info missing nickname/user_id"
                except Exception as exc:
                    login_status = "login_required"
                    state.error_code = smoke_errors.NETWORK_ERROR
                    state.error_message = f"self_info failed: {exc}"

            payload = {
                "login_status": login_status,
                "account_hint": account_hint,
                "current_url": page.url,
            }
            state.diagnostics.update(payload)
            await self._capture_artifacts(page, state, base_name=base_name)
            final_status = "success" if login_status == "valid" else "failed"
            return self._finalize_report(
                state,
                total_started,
                capability="login_check",
                items=[],
                item_count=0,
                payload=payload,
                status=final_status,
                error_code=None if login_status == "valid" else state.error_code,
                error_message=None if login_status == "valid" else state.error_message,
            )
        finally:
            await self._close_session()

    async def _run_homefeed(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        page = await self._acquire_page(state)
        base_name = f"homefeed_{self.run_id}"
        try:
            if not page:
                return self._finalize_report(state, total_started, capability="homefeed", items=[])
            probe = XhsHomeFeedProbe(target_count=self.options.max_items)
            candidates, report = await probe.collect(page)
            perf = report.get("perf") or {}
            state.timings_ms["page_goto"] = float(report.get("page_goto_ms") or perf.get("page_goto_ms") or 0)
            state.timings_ms["initial_wait"] = float(perf.get("initial_wait_ms") or 0)
            state.timings_ms["scroll"] = float(perf.get("scroll_ms") or report.get("scroll_ms") or 0)
            state.timings_ms["dom_extract"] = float(perf.get("dom_extract_ms") or 0)
            items = []
            for index, candidate in enumerate(candidates, start=1):
                items.append(_feed_item(candidate, rank_field="feed_position", rank_value=index))
            valid_items = [
                item
                for item in items
                if item.get("title") or item.get("cover_url") or item.get("canonical_url")
            ]
            missing = _count_missing(items, ["title", "cover_url", "canonical_url", "author_name"])
            await self._capture_artifacts(page, state, base_name=base_name)
            return self._finalize_report(
                state,
                total_started,
                capability="homefeed",
                items=items,
                item_count=len(valid_items),
                missing_fields=missing,
                partial=len(valid_items) >= 1 and len(valid_items) < 10,
            )
        finally:
            await self._close_session()

    async def _run_search_suggest(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        keyword = (self.options.keyword or "医学").strip()
        page = await self._acquire_page(state)
        base_name = f"search_suggest_{self.run_id}"
        try:
            if not page:
                return self._finalize_report(state, total_started, capability="search_suggest", items=[])
            probe = XhsSearchSuggestProbe(core_keyword=keyword)
            suggestions, report = await probe.collect(page)
            state.timings_ms["page_goto"] = float(report.get("total_ms") or 0)
            state.timings_ms["dom_extract"] = float(report.get("total_ms") or 0)
            filtered = [item for item in suggestions if item.get("suggested_keyword") != keyword]
            payload = {"core_keyword": keyword, "suggestions": filtered}
            await self._capture_artifacts(page, state, base_name=base_name)
            return self._finalize_report(
                state,
                total_started,
                capability="search_suggest",
                items=filtered,
                item_count=len(filtered),
                payload=payload,
                partial=len(filtered) >= 1 and len(filtered) < 5,
            )
        finally:
            await self._close_session()

    async def _run_search_collect(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        keyword = (self.options.keyword or "医学sci求助").strip()
        requested = build_search_filter_context(
            search_sort=self.options.search_sort,
            note_type=self.options.note_type,
            publish_time=self.options.publish_time,
        )
        page = await self._acquire_page(state)
        base_name = f"search_collect_{self.run_id}"
        applied_context = None
        filter_status = "not_applicable" if filters_are_default(requested) else "not_implemented"
        try:
            if not page:
                return self._finalize_report(
                    state,
                    total_started,
                    capability="search_collect",
                    items=[],
                    requested_filter_context=requested,
                    applied_filter_context=None,
                    filter_apply_status=filter_status,
                )

            from urllib.parse import quote

            goto_started = time.perf_counter()
            await page.goto(
                f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            state.timings_ms["page_goto"] = round((time.perf_counter() - goto_started) * 1000, 2)
            await page.wait_for_timeout(1200)
            state.timings_ms["initial_wait"] = 1200.0

            if not filters_are_default(requested):
                applied_context, filter_status, filter_diag, filter_ms = await apply_search_filters(
                    page,
                    search_sort=self.options.search_sort,
                    note_type=self.options.note_type,
                    publish_time=self.options.publish_time,
                )
                state.timings_ms["filter_apply"] = filter_ms
                state.diagnostics["filter_diagnostics"] = filter_diag

            probe = XhsSearchProbe(
                keywords=[keyword],
                max_items=self.options.max_items,
                search_sort=self.options.search_sort,
                note_type=self.options.note_type,
                publish_time=self.options.publish_time,
                skip_initial_goto=True,
            )
            candidates, report = await probe.collect(page)
            perf = report.get("perf") or {}
            state.timings_ms["scroll"] = float(perf.get("scroll_ms") or 0)
            state.timings_ms["dom_extract"] = float(perf.get("dom_extract_ms") or 0)

            items = []
            for index, candidate in enumerate(candidates, start=1):
                item = _feed_item(candidate, rank_field="search_rank", rank_value=index)
                item["search_keyword"] = keyword
                item["requested_filter_context"] = requested
                item["applied_filter_context"] = applied_context
                item["filter_apply_status"] = filter_status if not filters_are_default(requested) else "not_applicable"
                items.append(item)

            missing = _count_missing(items, ["platform_content_id", "canonical_url", "title", "search_keyword", "search_rank"])
            await self._capture_artifacts(page, state, base_name=base_name)
            return self._finalize_report(
                state,
                total_started,
                capability="search_collect",
                items=items,
                item_count=len(items),
                requested_filter_context=requested,
                applied_filter_context=applied_context,
                filter_apply_status=filter_status,
                missing_fields=missing,
                partial=len(items) >= 1 and len(items) < 10,
            )
        finally:
            await self._close_session()

    async def _run_detail(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        note_url = self.options.note_url
        if not note_url:
            return self._finalize_report(
                state,
                total_started,
                capability="detail",
                items=[],
                error_code=smoke_errors.UNKNOWN_ERROR,
                error_message="--note-url is required for detail capability",
            )
        page = await self._acquire_page(state)
        base_name = f"detail_{self.run_id}"
        try:
            if not page:
                return self._finalize_report(state, total_started, capability="detail", items=[])
            parsed = parse_xhs_note_context(note_url)
            if not parsed:
                return self._finalize_report(
                    state,
                    total_started,
                    capability="detail",
                    items=[],
                    error_code=smoke_errors.UNKNOWN_ERROR,
                    error_message=f"unable to parse note url: {note_url}",
                )
            platform_context = merge_xhs_context(context_from_url_and_raw(note_url), parsed.to_payload())
            probe = XhsDetailProbe()
            goto_started = time.perf_counter()
            snapshot = await probe.fetch_detail(
                page,
                canonical_url=note_url,
                platform_content_id=parsed.note_id,
                platform_context=platform_context,
            )
            state.timings_ms["page_goto"] = round((time.perf_counter() - goto_started) * 1000, 2)
            raw_payload = dict(snapshot.raw_payload or {})
            platform_tags = raw_payload.get("platform_tags")
            if not isinstance(platform_tags, list):
                platform_tags = []
            payload = {
                "platform_content_id": parsed.note_id,
                "canonical_url": note_url,
                "title": snapshot.title,
                "body_text": snapshot.body_text,
                "author_name": snapshot.author_name,
                "publish_time": snapshot.publish_time.isoformat() if snapshot.publish_time else "",
                "image_urls": snapshot.image_urls or [],
                "platform_tags": platform_tags,
                "like_count": snapshot.like_count,
                "comment_count": snapshot.comment_count,
                "collect_count": snapshot.collect_count,
                "raw_payload": raw_payload,
            }
            populated_groups = sum(
                1
                for key in ("title", "body_text", "author_name", "image_urls")
                if payload.get(key) not in (None, "", [])
            )
            missing = _count_missing([payload], ["title", "body_text", "author_name", "image_urls"])
            state.diagnostics["populated_field_groups"] = populated_groups
            await self._capture_artifacts(page, state, base_name=base_name)
            status = "success" if populated_groups >= 3 else ("partial" if populated_groups >= 1 else "failed")
            return self._finalize_report(
                state,
                total_started,
                capability="detail",
                items=[payload],
                item_count=1,
                payload=payload,
                status=status,
                missing_fields=missing,
                partial=status == "partial",
            )
        finally:
            await self._close_session()

    async def _run_comments(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        note_url = self.options.note_url
        if not note_url:
            return self._finalize_report(
                state,
                total_started,
                capability="comments",
                items=[],
                error_code=smoke_errors.UNKNOWN_ERROR,
                error_message="--note-url is required for comments capability",
            )
        page = await self._acquire_page(state)
        base_name = f"comments_{self.run_id}"
        try:
            if not page:
                return self._finalize_report(state, total_started, capability="comments", items=[])
            parsed = parse_xhs_note_context(note_url)
            if not parsed:
                return self._finalize_report(
                    state,
                    total_started,
                    capability="comments",
                    items=[],
                    error_code=smoke_errors.UNKNOWN_ERROR,
                    error_message=f"unable to parse note url: {note_url}",
                )
            platform_context = merge_xhs_context(context_from_url_and_raw(note_url), parsed.to_payload())
            probe = XhsCommentProbe()
            result = await probe.fetch_comments_result(
                page,
                canonical_url=note_url,
                platform_content_id=parsed.note_id,
                platform_context=platform_context,
                limit=self.options.max_items,
            )
            if result.error_code:
                mapped = result.error_code
                if mapped in {"login_required", "missing_xsec_context", "comment_surface_unavailable", "dom_structure_changed"}:
                    code = smoke_errors.LOGIN_REQUIRED if mapped == "login_required" else smoke_errors.SELECTOR_NOT_FOUND
                else:
                    code = smoke_errors.DOM_EXTRACT_FAILED
                await self._capture_artifacts(page, state, base_name=base_name)
                if result.surface_status == "comments_disabled" or (not result.comments and result.surface_status == "ok"):
                    payload = {"message": result.message or "该笔记无可见评论"}
                    return self._finalize_report(
                        state,
                        total_started,
                        capability="comments",
                        items=[],
                        item_count=0,
                        payload=payload,
                        status="success",
                    )
                return self._finalize_report(
                    state,
                    total_started,
                    capability="comments",
                    items=[],
                    error_code=code,
                    error_message=result.message,
                )

            items = []
            for index, comment in enumerate(result.comments[: self.options.max_items], start=1):
                items.append(
                    {
                        "comment_id": comment.platform_comment_id,
                        "comment_text": comment.body_text,
                        "comment_author": comment.author_name,
                        "like_count": comment.like_count,
                        "comment_time": comment.created_time.isoformat() if comment.created_time else "",
                        "comment_rank": index,
                        "raw_payload": comment.raw_payload or {},
                    }
                )
            missing = _count_missing(items, ["comment_id", "comment_text", "comment_author"])
            await self._capture_artifacts(page, state, base_name=base_name)
            return self._finalize_report(
                state,
                total_started,
                capability="comments",
                items=items,
                item_count=len(items),
                missing_fields=missing,
                partial=len(items) >= 1 and len(items) < 10,
            )
        finally:
            await self._close_session()

    async def _run_creator_notes(self, state: _RunState) -> dict[str, Any]:
        total_started = time.perf_counter()
        creator_url = self.options.creator_url
        if not creator_url:
            return self._finalize_report(
                state,
                total_started,
                capability="creator_notes",
                items=[],
                error_code=smoke_errors.UNKNOWN_ERROR,
                error_message="--creator-url is required for creator_notes capability",
            )
        page = await self._acquire_page(state)
        base_name = f"creator_notes_{self.run_id}"
        try:
            if not page:
                return self._finalize_report(state, total_started, capability="creator_notes", items=[])
            creator_context = parse_xhs_creator_context(creator_url)
            connector = XhsCreatorConnector()
            fetch_started = time.perf_counter()
            result = await connector.fetch_latest(
                page,
                creator_profile_url=creator_url,
                creator_platform_id=creator_context.creator_platform_id,
                context=creator_context.to_payload(),
                limit=self.options.max_items,
            )
            state.timings_ms["dom_extract"] = round((time.perf_counter() - fetch_started) * 1000, 2)
            notes = []
            for index, item in enumerate(result.items[: self.options.max_items], start=1):
                notes.append(
                    {
                        "platform_content_id": item.platform_content_id,
                        "canonical_url": item.canonical_url,
                        "title": item.title_or_summary,
                        "cover_url": item.cover_url,
                        "visible_like_count": None,
                        "creator_note_rank": index,
                    }
                )
            payload = {
                "creator_name": result.creator_display_name,
                "creator_id": result.creator_platform_id,
                "profile_url": creator_url,
                "follower_count": (result.raw_payload or {}).get("follower_count"),
                "notes": notes,
            }
            valid_notes = [note for note in notes if note.get("title") or note.get("cover_url") or note.get("canonical_url")]
            missing = _count_missing(notes, ["platform_content_id", "canonical_url", "title"])
            await self._capture_artifacts(page, state, base_name=base_name)
            return self._finalize_report(
                state,
                total_started,
                capability="creator_notes",
                items=notes,
                item_count=len(valid_notes),
                payload=payload,
                missing_fields=missing,
                partial=len(valid_notes) >= 1 and len(valid_notes) < 3,
            )
        except Exception as exc:
            await self._capture_artifacts(page, state, base_name=base_name)
            return self._finalize_report(
                state,
                total_started,
                capability="creator_notes",
                items=[],
                error_code=smoke_errors.DOM_EXTRACT_FAILED,
                error_message=str(exc),
            )
        finally:
            await self._close_session()
