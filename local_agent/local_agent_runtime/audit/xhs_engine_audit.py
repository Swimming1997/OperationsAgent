from __future__ import annotations

import httpx
import time
import uuid
from pathlib import Path
from typing import Any

from local_agent_runtime.audit.compare import field_coverage
from local_agent_runtime.audit.levels import AuditSeverity
from local_agent_runtime.audit.logger import EngineAuditLogger, downloaded_media_to_dict, serialize_comment_item, serialize_detail_item
from local_agent_runtime.audit.media_downloader import download_media_files
from local_agent_runtime.audit.models import EngineAuditIssue, EngineAuditRecord, EngineAuditRunSummary
from local_agent_runtime.audit.note_bundle import (
    build_note_bundle_payload,
    compose_note_bundle_record,
    media_download_issues,
)
from local_agent_runtime.audit.perf import PerfTimer, merge_surface_perf
from local_agent_runtime.audit.redaction import redact_url
from local_agent_runtime.audit.summary import engine_audit_summary
from local_agent_runtime.connectors.xhs.api_client import (
    XhsApiClient,
    XhsApiError,
    XhsApiUnavailable,
    browser_context_cookie_header,
    build_self_info_account_summary,
    classify_self_info_severity,
    extract_self_info_result,
    write_self_info_raw_fields_debug,
)
from local_agent_runtime.connectors.xhs.capabilities import get_xhs_capability, list_xhs_capabilities
from local_agent_runtime.connectors.xhs.comment_probe import XhsCommentProbe
from local_agent_runtime.connectors.xhs.context import build_xhs_note_url, context_from_url_and_raw, enrich_xhs_context_from_page
from local_agent_runtime.connectors.xhs.creator import XhsCreatorConnector
from local_agent_runtime.connectors.xhs.detail_probe import XhsDetailProbe
from local_agent_runtime.connectors.xhs.homefeed_probe import XhsHomeFeedProbe
from local_agent_runtime.connectors.xhs.normalizer import normalize_search_api_items, search_api_field_stats
from local_agent_runtime.connectors.xhs.search_probe import XhsSearchProbe
from local_agent_runtime.config import load_agent_runtime_config
from local_agent_runtime.contracts import FeedCandidateInput
from local_agent_runtime.enums import SessionStatus
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider

SURFACE_CAPABILITY = {
    "self_info": "xhs.account.self_info",
    "homefeed": "xhs.feed.home_recommend",
    "search": "xhs.search.notes",
    "search_api": "xhs.search.notes_api",
    "detail": "xhs.note.detail",
    "comment": "xhs.note.comments",
    "note_bundle": "xhs.note.bundle",
    "creator": "xhs.creator.posted_notes",
    "smoke": "xhs.engine.smoke",
}


def should_flag_note_unavailable(*, title: str, body_text: str | None, api_success: bool) -> bool:
    if title == "当前笔记暂时无法浏览" or "暂时无法浏览" in str(title):
        return True
    return not title and not body_text and not api_success


def pick_fresh_note(candidates: list[FeedCandidateInput]) -> tuple[str, str, dict[str, Any]] | None:
    ordered = sorted(
        candidates,
        key=lambda item: 0 if (item.platform_context or {}).get("api_detail_ready") else 1,
    )
    for candidate in ordered:
        note_id = candidate.platform_content_id
        if not note_id:
            continue
        context = dict(candidate.platform_context or {})
        url = candidate.canonical_url or build_xhs_note_url(context)
        if not url:
            continue
        return url, note_id, context
    return None


class XhsEngineAuditor:
    def __init__(self, *, project_root: Path, config_path: Path | None = None):
        self.project_root = project_root
        self.config_path = config_path

    async def run(
        self,
        *,
        surfaces: list[str],
        keyword: str | None = None,
        target_count: int = 20,
        limit: int = 20,
        limit_comments: int = 20,
        url: str | None = None,
        creator_url: str | None = None,
    ) -> tuple[EngineAuditRunSummary, EngineAuditLogger]:
        run_id = time.strftime("%Y%m%d") + "_" + uuid.uuid4().hex[:12]
        started = time.perf_counter()
        records: list[EngineAuditRecord] = []
        homefeed_items: list[FeedCandidateInput] = []
        search_api_items: list[dict[str, Any]] = []
        detail_items: list[dict[str, Any]] = []
        comment_items: list[dict[str, Any]] = []
        note_bundle_parts: dict[str, Any] | None = None
        if "capabilities" in surfaces:
            records.append(self._capabilities_record())
        if "smoke" in surfaces:
            records.extend(
                await self._run_smoke(
                    keyword=keyword or "SCI投稿",
                    limit=limit,
                    run_id=run_id,
                )
            )
        browser_surfaces = [item for item in surfaces if item not in {"capabilities", "smoke"}]
        if browser_surfaces:
            note_bundle_parts = {} if "note_bundle" in browser_surfaces else None
            records.extend(
                await self._run_browser_surfaces(
                    browser_surfaces,
                    run_id=run_id,
                    homefeed_items=homefeed_items,
                    search_api_items=search_api_items,
                    detail_items=detail_items,
                    comment_items=comment_items,
                    note_bundle_parts=note_bundle_parts,
                    keyword=keyword,
                    target_count=target_count,
                    limit=limit,
                    limit_comments=limit_comments,
                    url=url,
                    creator_url=creator_url,
                )
            )
        logger = EngineAuditLogger(project_root=self.project_root, run_id=run_id)
        artifacts: dict[str, str] = {}
        if note_bundle_parts:
            bundle_record, bundle_artifacts = await self._finalize_note_bundle(
                logger,
                note_bundle_parts,
                run_id=run_id,
                total_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            records.append(bundle_record)
            artifacts.update(bundle_artifacts)
        if homefeed_items:
            artifacts.update(logger.write_homefeed_items(homefeed_items))
        if search_api_items:
            artifacts.update(logger.write_search_api_items(search_api_items))
        if detail_items and not note_bundle_parts:
            detail_item = await self._finalize_detail_item(logger, detail_items[0])
            artifacts.update(logger.write_detail_item(detail_item))
        if comment_items and not note_bundle_parts:
            artifacts.update(logger.write_comment_items(comment_items))
        summary = EngineAuditRunSummary(
            run_id=run_id,
            records=records,
            total_ms=round((time.perf_counter() - started) * 1000, 2),
            artifacts=artifacts,
        )
        logger.write_records(records)
        logger.write_summary(summary)
        return summary, logger

    def _capabilities_record(self) -> EngineAuditRecord:
        capabilities = [
            {
                "key": item.key,
                "layer": item.layer.value,
                "status": item.status.value,
                "description": item.description,
                "current_impl": item.current_impl,
                "mediacrawler_reference": item.mediacrawler_reference,
                "required_context": item.required_context,
                "output_contract": item.output_contract,
                "audit_supported": item.audit_supported,
                "notes": item.notes,
            }
            for item in list_xhs_capabilities()
        ]
        return EngineAuditRecord(
            capability_key="xhs.engine.capabilities",
            surface="capabilities",
            status="ok",
            severity=AuditSeverity.P4_INFO,
            items_seen=len(capabilities),
            normalized_items=len(capabilities),
            source_path="capability_registry",
            payload={"capabilities": capabilities},
        )

    async def _run_smoke(self, *, keyword: str, limit: int, run_id: str) -> list[EngineAuditRecord]:
        if not self.config_path:
            return [self._skip_record("smoke", "missing_config", "smoke 模式需要 --config 才能连接本地浏览器会话。")]
        config = load_agent_runtime_config(self.config_path)
        session_meta: dict[str, Any] = {}
        if config.cdp_url:
            session_meta = {"cdp_url": config.cdp_url, "probe_only": True}
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY or not session.page:
            await session.close()
            return self._session_failed_records(["smoke"], session)
        records: list[EngineAuditRecord] = []
        selection_source = "search"
        try:
            self_info = await self._audit_self_info(session.page, run_id=run_id)
            records.append(self_info)
            search_record, search_items = await self._collect_search(session.page, keyword=keyword, limit=limit)
            records.append(search_record)
            selected = pick_fresh_note(search_items)
            selection_source = "search"
            homefeed_collected: list[FeedCandidateInput] = []
            if not selected or not (selected[2].get("api_detail_ready")):
                homefeed_record, homefeed_collected = await self._collect_homefeed(session.page, target_count=limit)
                records.append(homefeed_record)
                home_selected = pick_fresh_note(homefeed_collected)
                if home_selected and home_selected[2].get("api_detail_ready"):
                    selected = home_selected
                    selection_source = "homefeed"
                elif not selected:
                    selected = home_selected
                    selection_source = "homefeed"
            if not selected:
                records.append(
                    EngineAuditRecord(
                        capability_key="xhs.engine.smoke",
                        surface="smoke",
                        status="failed",
                        severity=AuditSeverity.P1_BLOCKER,
                        issues=[
                            EngineAuditIssue(
                                AuditSeverity.P1_BLOCKER,
                                "xhs.engine.smoke",
                                "smoke",
                                "no_fresh_note_url",
                                "search/homefeed 均未找到可用于 detail/comment 的新鲜笔记 URL。",
                                {"keyword": keyword},
                                "确认已登录并能在搜索/推荐页看到笔记卡片。",
                            )
                        ],
                        source_path="smoke_selector",
                        payload={"keyword": keyword, "selection_source": selection_source},
                    )
                )
                return records
            url, note_id, platform_context = selected
            upstream_author_name = next(
                (item.author_name for item in search_items + homefeed_collected if item.platform_content_id == note_id),
                None,
            )
            if not platform_context.get("api_detail_ready"):
                url, platform_context = await enrich_xhs_context_from_page(
                    session.page,
                    url=url,
                    note_id=note_id,
                    platform_context=platform_context,
                )
            detail_record = await self._audit_detail(
                session.page,
                url=url,
                platform_context=platform_context,
                selection_source=selection_source,
                upstream_author_name=upstream_author_name,
                source_surface=selection_source,
            )
            comment_record = await self._audit_comment(session.page, url=url, platform_context=platform_context, limit=limit)
            records.extend([detail_record, comment_record])
            from local_agent_runtime.audit.levels import highest_severity

            records.append(
                EngineAuditRecord(
                    capability_key="xhs.engine.smoke",
                    surface="smoke",
                    status="ok" if detail_record.severity == AuditSeverity.P4_INFO and comment_record.severity == AuditSeverity.P4_INFO else "partial",
                    severity=highest_severity([self_info.severity, search_record.severity, detail_record.severity, comment_record.severity]),
                    items_seen=1,
                    normalized_items=1,
                    source_path="smoke_chain",
                    payload={
                        "keyword": keyword,
                        "selection_source": selection_source,
                        "selected_note_id": note_id,
                        "selected_url_redacted": redact_url(url),
                        "has_xsec_context": bool(platform_context.get("api_detail_ready")),
                        "api_detail_ready": bool(platform_context.get("api_detail_ready")),
                        "sub_surfaces": {
                            "self_info": self_info.status,
                            "search": search_record.status,
                            "detail": detail_record.status,
                            "comment": comment_record.status,
                        },
                    },
                )
            )
            return records
        finally:
            await session.close()

    def _session_failed_records(self, surfaces: list[str], session) -> list[EngineAuditRecord]:
        session_severity = AuditSeverity.P0_FATAL
        issue_code = "session_not_ready"
        if session.status == SessionStatus.EXPIRED:
            session_severity = AuditSeverity.P1_BLOCKER
            issue_code = "login_required"
        elif session.status == SessionStatus.MANUAL_VERIFY_REQUIRED:
            session_severity = AuditSeverity.P1_BLOCKER
            issue_code = "manual_verify_required"
        elif session.status == SessionStatus.UNAVAILABLE:
            session_severity = AuditSeverity.P0_FATAL
            issue_code = "session_unavailable"
        return [
            EngineAuditRecord(
                capability_key=SURFACE_CAPABILITY.get(surface, "xhs.unknown"),
                surface=surface,
                status="failed",
                severity=session_severity,
                issues=[
                    EngineAuditIssue(
                        severity=session_severity,
                        capability_key=SURFACE_CAPABILITY.get(surface, "xhs.unknown"),
                        surface=surface,
                        code=issue_code,
                        message=session.message or "XHS session is not ready",
                        evidence=session.diagnostics or {},
                        suggested_action="在本机 Chrome 完成小红书登录或手动验证后重试。",
                    )
                ],
                source_path="session_acquire",
            )
            for surface in surfaces
        ]

    async def _run_browser_surfaces(
        self,
        surfaces: list[str],
        *,
        run_id: str,
        homefeed_items: list[FeedCandidateInput],
        search_api_items: list[dict[str, Any]],
        detail_items: list[dict[str, Any]],
        comment_items: list[dict[str, Any]],
        note_bundle_parts: dict[str, Any] | None,
        **kwargs: Any,
    ) -> list[EngineAuditRecord]:
        if not self.config_path:
            return [
                self._skip_record(surface, "missing_config", "需要 --config 才能连接本地浏览器会话。")
                for surface in surfaces
            ]
        config = load_agent_runtime_config(self.config_path)
        session_meta: dict[str, Any] = {}
        if config.cdp_url:
            session_meta = {"cdp_url": config.cdp_url, "probe_only": True}
        session = await XhsBrowserSessionProvider().acquire(session_meta=session_meta)
        if session.status != SessionStatus.READY or not session.page:
            await session.close()
            return self._session_failed_records(surfaces, session)
        try:
            records: list[EngineAuditRecord] = []
            for surface in surfaces:
                if surface == "self_info":
                    records.append(await self._audit_self_info(session.page, run_id=run_id))
                elif surface == "homefeed":
                    records.append(
                        await self._audit_homefeed(
                            session.page,
                            target_count=int(kwargs.get("target_count") or 20),
                            homefeed_items=homefeed_items,
                        )
                    )
                elif surface == "search":
                    records.append(await self._audit_search(session.page, keyword=kwargs.get("keyword") or "SCI投稿", limit=int(kwargs.get("limit") or 20)))
                elif surface == "search_api":
                    records.append(
                        await self._audit_search_api(
                            session.page,
                            keyword=kwargs.get("keyword") or "SCI投稿",
                            limit=int(kwargs.get("limit") or 20),
                            search_api_items=search_api_items,
                        )
                    )
                elif surface == "detail":
                    url = kwargs.get("url")
                    if not url:
                        records.append(self._skip_record("detail", "missing_target_url", "未提供 --url，detail 审计跳过。"))
                    else:
                        records.append(
                            await self._audit_detail(
                                session.page,
                                url=str(url),
                                detail_items=detail_items,
                                upstream_author_name=kwargs.get("upstream_author_name"),
                                source_surface=kwargs.get("source_surface"),
                            )
                        )
                elif surface == "comment":
                    url = kwargs.get("url")
                    if not url:
                        records.append(self._skip_record("comment", "missing_target_url", "未提供 --url，comment 审计跳过。"))
                    else:
                        records.append(
                            await self._audit_comment(
                                session.page,
                                url=str(url),
                                limit=int(kwargs.get("limit") or 20),
                                comment_items=comment_items,
                            )
                        )
                elif surface == "note_bundle":
                    url = kwargs.get("url")
                    if not url:
                        records.append(self._skip_record("note_bundle", "missing_target_url", "未提供 --url，note_bundle 审计跳过。"))
                    elif note_bundle_parts is not None:
                        await self._collect_note_bundle(
                            session.page,
                            url=str(url),
                            limit_comments=int(kwargs.get("limit_comments") or 20),
                            note_bundle_parts=note_bundle_parts,
                        )
                elif surface == "creator":
                    creator_url = kwargs.get("creator_url")
                    if not creator_url:
                        records.append(self._skip_record("creator", "missing_creator_url", "未提供 --creator-url，creator 审计跳过。"))
                    else:
                        records.append(await self._audit_creator(session.page, creator_url=str(creator_url), limit=int(kwargs.get("limit") or 20)))
                else:
                    records.append(self._skip_record(surface, "unknown_surface", f"未知 surface: {surface}"))
            return records
        finally:
            await session.close()

    def _skip_record(self, surface: str, code: str, message: str) -> EngineAuditRecord:
        capability_key = SURFACE_CAPABILITY.get(surface, "xhs.unknown")
        return EngineAuditRecord(
            capability_key=capability_key,
            surface=surface,
            status="skipped",
            severity=AuditSeverity.P4_INFO,
            issues=[EngineAuditIssue(AuditSeverity.P4_INFO, capability_key, surface, code, message)],
            source_path="audit_cli",
        )

    async def _audit_self_info(self, page, *, run_id: str) -> EngineAuditRecord:
        timer = PerfTimer()
        raw_data: dict[str, Any] | None = None
        error_payload: dict[str, Any] = {}
        logged_in = False
        with timer.stage("api"):
            cookie_str = await browser_context_cookie_header(page.context)
            client = XhsApiClient(cookie_str=cookie_str)
            try:
                raw_data = await client.query_self()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body_text = exc.response.text[:300]
                if status in {401, 403}:
                    code = "login_required"
                elif status == 461 or "verify" in body_text.lower() or "验证" in body_text:
                    code = "manual_verify_required"
                else:
                    code = "api_http_failed"
                error_payload = {
                    "error_code": code,
                    "http_status": status,
                    "message": f"self_info HTTP {status}",
                }
            except XhsApiUnavailable as exc:
                error_payload = {"error_code": "api_signature_failed", "message": str(exc)}
            except XhsApiError as exc:
                message = str(exc)
                lowered = message.lower()
                if "login" in lowered or "登录" in message or "未登录" in message:
                    code = "login_required"
                elif "verify" in lowered or "验证" in message or "滑块" in message:
                    code = "manual_verify_required"
                else:
                    code = "api_http_failed"
                error_payload = {"error_code": code, "message": message[:300]}
            except Exception as exc:
                message = str(exc)
                lowered = message.lower()
                if "login" in lowered or "登录" in message:
                    code = "login_required"
                elif "verify" in lowered or "验证" in message:
                    code = "manual_verify_required"
                else:
                    code = "api_http_failed"
                error_payload = {"error_code": code, "message": message[:300]}
            else:
                extract_probe = extract_self_info_result(raw_data)
                logged_in = bool(extract_probe.nickname or extract_probe.user_id)
                if not logged_in:
                    error_payload = {
                        "error_code": "login_required",
                        "message": "self_info 未返回 nickname 或 user_id，当前会话未登录或资料不可用",
                    }
        timer.set_items(1 if logged_in else 0)
        if raw_data is not None:
            write_self_info_raw_fields_debug(project_root=self.project_root, run_id=run_id, data=raw_data)
        extract = extract_self_info_result(raw_data if logged_in else {})
        account_summary = build_self_info_account_summary(logged_in=logged_in, status="partial", extract=extract)
        severity = classify_self_info_severity(logged_in=logged_in, summary=account_summary)
        issues = []
        if not logged_in:
            issues.append(
                EngineAuditIssue(
                    severity=severity,
                    capability_key="xhs.account.self_info",
                    surface="self_info",
                    code=str(error_payload.get("error_code") or "login_required"),
                    message=str(error_payload.get("message") or "self_info failed"),
                    evidence={
                        "error_code": error_payload.get("error_code") or "login_required",
                        "message": error_payload.get("message") or "self_info failed",
                    },
                    suggested_action="确认登录态有效，必要时重新登录或处理安全验证。",
                )
            )
        elif severity == AuditSeverity.P3_MINOR:
            issues.append(
                EngineAuditIssue(
                    severity=severity,
                    capability_key="xhs.account.self_info",
                    surface="self_info",
                    code="self_info_avatar_missing",
                    message="登录态可用，但 avatar_url 等非核心展示字段缺失。",
                    evidence={"missing_fields": account_summary.get("missing_fields", [])},
                    suggested_action="检查 selfinfo 响应中的头像字段映射。",
                )
            )
        elif severity == AuditSeverity.P2_MAJOR:
            issues.append(
                EngineAuditIssue(
                    severity=severity,
                    capability_key="xhs.account.self_info",
                    surface="self_info",
                    code="self_info_identity_incomplete",
                    message="登录态可用，但账号身份闭环字段不完整。",
                    evidence={
                        "missing_fields": account_summary.get("missing_fields", []),
                        "missing_reasons": account_summary.get("missing_reasons", {}),
                    },
                    suggested_action="检查 selfinfo 响应结构、user_id 字段映射，或确认 API 是否返回 profile URL。",
                )
            )
        status = "failed"
        if logged_in:
            status = "ok" if severity == AuditSeverity.P4_INFO else "partial"
            account_summary = build_self_info_account_summary(logged_in=logged_in, status=status, extract=extract)
        return EngineAuditRecord(
            capability_key="xhs.account.self_info",
            surface="self_info",
            status=status,
            severity=severity,
            items_seen=1 if logged_in else 0,
            normalized_items=1 if logged_in else 0,
            field_coverage={
                "nickname": 1.0 if extract.nickname else 0.0,
                "user_id": 1.0 if extract.user_id else 0.0,
                "red_id": 1.0 if extract.red_id else 0.0,
                "home_url": 1.0 if extract.home_url else 0.0,
                "avatar_url": 1.0 if extract.avatar_url else 0.0,
            },
            perf=timer.summary(),
            issues=issues,
            source_path="signed_api_selfinfo",
            payload={"logged_in": logged_in, "raw_fields_debug": f"self_info_raw_fields_{run_id}.json"},
            account_summary=account_summary,
        )

    async def _collect_homefeed(self, page, *, target_count: int) -> tuple[EngineAuditRecord, list[FeedCandidateInput]]:
        timer = PerfTimer()
        items, report = await XhsHomeFeedProbe(target_count=target_count).collect(page)
        timer.set_items(len(items))
        perf = merge_surface_perf(timer, report.get("perf"), item_count=len(items))
        record = EngineAuditRecord(
            "xhs.feed.home_recommend",
            "homefeed",
            "ok",
            AuditSeverity.P4_INFO,
            report.get("raw_cards_seen", len(items)),
            len(items),
            report.get("field_coverage") or {},
            perf,
            [],
            report.get("source_path"),
            report,
        )
        return record, items

    async def _collect_search(self, page, *, keyword: str, limit: int) -> tuple[EngineAuditRecord, list[FeedCandidateInput]]:
        timer = PerfTimer()
        items, report = await XhsSearchProbe(keywords=[keyword], max_items=limit).collect(page)
        timer.set_items(len(items))
        severity = AuditSeverity.P3_MINOR if not items else AuditSeverity.P4_INFO
        issues = []
        if not items:
            issues.append(EngineAuditIssue(severity, "xhs.search.notes", "search", "normalization_empty", "搜索未得到可归一化结果。", {"keyword": keyword}))
        record = EngineAuditRecord(
            "xhs.search.notes",
            "search",
            "ok" if items else "empty",
            severity,
            report.get("raw_cards_seen", len(items)),
            len(items),
            report.get("field_coverage") or {},
            merge_surface_perf(timer, report.get("perf"), item_count=len(items)),
            issues,
            report.get("source_path"),
            report,
        )
        return record, items

    async def _audit_homefeed(
        self,
        page,
        *,
        target_count: int,
        homefeed_items: list[FeedCandidateInput],
    ) -> EngineAuditRecord:
        record, items = await self._collect_homefeed(page, target_count=target_count)
        homefeed_items.extend(items)
        return record

    async def _audit_search(self, page, *, keyword: str, limit: int) -> EngineAuditRecord:
        record, _items = await self._collect_search(page, keyword=keyword, limit=limit)
        return record

    async def _finalize_detail_item(self, logger: EngineAuditLogger, item: dict[str, Any]) -> dict[str, Any]:
        note_id = str(item.get("note_id") or "unknown")
        media_dir = logger.detail_media_dir(note_id)
        downloaded = await download_media_files(
            list(item.get("image_urls") or []),
            media_dir,
            relative_to=logger.output_dir,
        )
        return {
            **item,
            "downloaded_images": downloaded_media_to_dict(downloaded),
        }

    async def _collect_note_bundle(
        self,
        page,
        *,
        url: str,
        limit_comments: int,
        note_bundle_parts: dict[str, Any],
    ) -> None:
        platform_context = context_from_url_and_raw(url, source_surface="manual_url")
        resolved_url = build_xhs_note_url(platform_context, fallback_url=url, source_surface="manual_url") or url
        detail_items: list[dict[str, Any]] = []
        detail_snapshots: list[dict[str, Any]] = []
        comment_items: list[dict[str, Any]] = []
        detail_record = await self._audit_detail(
            page,
            url=resolved_url,
            platform_context=platform_context,
            source_surface="manual_url",
            detail_items=detail_items,
            detail_snapshots=detail_snapshots,
        )
        comment_record = await self._audit_comment(
            page,
            url=resolved_url,
            platform_context=platform_context,
            limit=limit_comments,
            comment_items=comment_items,
        )
        note_bundle_parts.update(
            {
                "input_url": url,
                "resolved_url": resolved_url,
                "platform_context": platform_context,
                "detail_item": detail_items[0] if detail_items else None,
                "detail_snapshot": detail_snapshots[0] if detail_snapshots else {},
                "comment_items": comment_items,
                "detail_record": detail_record,
                "comment_record": comment_record,
            }
        )

    async def _finalize_note_bundle(
        self,
        logger: EngineAuditLogger,
        note_bundle_parts: dict[str, Any],
        *,
        run_id: str,
        total_ms: float,
    ) -> tuple[EngineAuditRecord, dict[str, str]]:
        detail_item = note_bundle_parts.get("detail_item")
        detail_record = note_bundle_parts["detail_record"]
        comment_record = note_bundle_parts["comment_record"]
        if not detail_item:
            failed_record = EngineAuditRecord(
                capability_key="xhs.note.bundle",
                surface="note_bundle",
                status="failed",
                severity=detail_record.severity,
                issues=[*detail_record.issues, *comment_record.issues],
                source_path="note_bundle",
                payload={"input_url": note_bundle_parts.get("input_url")},
            )
            return failed_record, {}
        finalized_detail = await self._finalize_detail_item(logger, detail_item)
        media_issues = media_download_issues(finalized_detail.get("downloaded_images") or [])
        note_id = str(finalized_detail.get("note_id") or "unknown")
        artifact_names = {
            "note_bundle_json": f"engine_audit_{logger.run_id}.note_bundle.json",
            "note_bundle_md": f"engine_audit_{logger.run_id}.note_bundle.md",
            "note_bundle_media_dir": f"media/detail_{note_id}/",
        }
        bundle = build_note_bundle_payload(
            run_id=run_id,
            input_url=str(note_bundle_parts.get("input_url") or ""),
            platform_context=dict(note_bundle_parts.get("platform_context") or {}),
            detail_item=finalized_detail,
            detail_snapshot=dict(note_bundle_parts.get("detail_snapshot") or {}),
            comment_items=list(note_bundle_parts.get("comment_items") or []),
            detail_record=detail_record,
            comment_record=comment_record,
            extra_issues=media_issues,
            artifacts=artifact_names,
            total_ms=total_ms,
        )
        bundle_artifacts = logger.write_note_bundle(bundle)
        perf = {
            **(detail_record.perf or {}),
            **{f"comment_{key}": value for key, value in (comment_record.perf or {}).items()},
            "total_ms": total_ms,
        }
        bundle_record = compose_note_bundle_record(
            bundle=bundle,
            detail_record=detail_record,
            comment_record=comment_record,
            extra_issues=media_issues,
            perf=perf,
        )
        return bundle_record, bundle_artifacts

    async def _audit_search_api(
        self,
        page,
        *,
        keyword: str,
        limit: int,
        search_api_items: list[dict[str, Any]],
    ) -> EngineAuditRecord:
        timer = PerfTimer()
        with timer.stage("api"):
            cookie_str = await browser_context_cookie_header(page.context)
            data = await XhsApiClient(cookie_str=cookie_str).search_notes(keyword=keyword, page_size=limit)
        items = normalize_search_api_items(data, keyword=keyword, limit=limit)
        search_api_items.extend(items)
        stats = search_api_field_stats(items)
        timer.set_items(len(items))
        severity = AuditSeverity.P4_INFO if items else AuditSeverity.P2_MAJOR
        issues = []
        if not items:
            issues.append(
                EngineAuditIssue(
                    severity,
                    "xhs.search.notes_api",
                    "search_api",
                    "search_api_empty",
                    "search API 未返回可归一化 items。",
                    {"keyword": keyword},
                )
            )
        payload = {**stats, "keyword": keyword, "sample_items": items[:10]}
        return EngineAuditRecord(
            "xhs.search.notes_api",
            "search_api",
            "ok" if items else "empty",
            severity,
            stats.get("items_count", 0),
            stats.get("items_with_id", 0),
            {
                "items_with_xsec_token": stats.get("items_with_xsec_token", 0) / max(stats.get("items_count", 0), 1),
                "items_with_xsec_source": stats.get("items_with_xsec_source", 0) / max(stats.get("items_count", 0), 1),
                "detail_ready_count": stats.get("detail_ready_count", 0) / max(stats.get("items_count", 0), 1),
            },
            timer.summary(),
            issues,
            "signed_api_search_notes",
            payload,
        )

    async def _audit_detail(
        self,
        page,
        *,
        url: str,
        platform_context: dict[str, Any] | None = None,
        selection_source: str | None = None,
        upstream_author_name: str | None = None,
        source_surface: str | None = None,
        detail_items: list[dict[str, Any]] | None = None,
        detail_snapshots: list[dict[str, Any]] | None = None,
    ) -> EngineAuditRecord:
        note_id = url.rstrip("/").split("/")[-1].split("?")[0]
        timer = PerfTimer()
        with timer.stage("api"):
            snapshot = await XhsDetailProbe().fetch_detail(
                page,
                canonical_url=url,
                platform_content_id=note_id,
                platform_context=platform_context or {},
                source_surface=source_surface or selection_source,
                upstream_author_name=upstream_author_name,
            )
        timer.set_items(1)
        payload = snapshot.model_dump(mode="json")
        raw_payload = payload.get("raw_payload") or {}
        dom_fallback = raw_payload.get("dom_fallback") if isinstance(raw_payload, dict) else {}
        fetch_source = (dom_fallback or {}).get("fetch_source") or "unknown"
        canonical_url = (dom_fallback or {}).get("canonical_url") or url
        title = payload.get("title") or ""
        author_name = payload.get("author_name") or ""
        suspect_author = bool((dom_fallback or {}).get("suspect_author"))
        api_success = bool((dom_fallback or {}).get("api_success"))
        coverage = field_coverage(
            [{**payload, "canonical_url": canonical_url}],
            ["title", "body_text", "author_name", "canonical_url", "image_urls"],
        )
        issues = []
        severity = AuditSeverity.P4_INFO
        if should_flag_note_unavailable(title=title, body_text=payload.get("body_text"), api_success=api_success):
            severity = AuditSeverity.P2_MAJOR
            issues.append(
                EngineAuditIssue(
                    severity=severity,
                    capability_key="xhs.note.detail",
                    surface="detail",
                    code="note_unavailable",
                    message="笔记页面不可浏览，可能需要登录或 App 扫码。",
                    evidence={"fetch_source": fetch_source, "title": title, "selection_source": selection_source},
                    suggested_action="确认登录态有效，或换用 search/homefeed 新鲜 URL。",
                )
            )
        elif fetch_source != "api" or suspect_author or not canonical_url or not author_name:
            severity = AuditSeverity.P2_MAJOR
            code = "dom_fallback_untrusted"
            if suspect_author:
                code = "suspect_author"
            elif (dom_fallback or {}).get("api_error_code"):
                code = str((dom_fallback or {}).get("api_error_code"))
            issues.append(
                EngineAuditIssue(
                    severity=severity,
                    capability_key="xhs.note.detail",
                    surface="detail",
                    code=code,
                    message=str((dom_fallback or {}).get("api_error_message") or "detail 未通过 API 拿到可信字段"),
                    evidence={
                        "fetch_source": fetch_source,
                        "author_name": author_name,
                        "upstream_author_name": upstream_author_name,
                        "suspect_author": suspect_author,
                        "canonical_url": canonical_url,
                        "api_success": api_success,
                    },
                )
            )
        detail_item = serialize_detail_item(note_id=note_id, url=url, snapshot=payload, diagnostics=dom_fallback or {})
        if detail_items is not None:
            detail_items.append(detail_item)
        if detail_snapshots is not None:
            detail_snapshots.append(payload)
        status = "ok" if severity == AuditSeverity.P4_INFO else "partial"
        slim_payload = {
            **{k: v for k, v in detail_item.items() if k != "body_text"},
            "body_text_preview": (detail_item.get("body_text") or "")[:300],
            "selection_source": selection_source,
            "selected_url_redacted": redact_url(url),
            "api_error_code": (dom_fallback or {}).get("api_error_code"),
            "api_error_message": (dom_fallback or {}).get("api_error_message"),
            "downloaded_images_ok": sum(1 for item in detail_item.get("downloaded_images") or [] if item.get("status") == "ok"),
            "downloaded_images_failed": sum(1 for item in detail_item.get("downloaded_images") or [] if item.get("status") == "failed"),
        }
        return EngineAuditRecord(
            "xhs.note.detail",
            "detail",
            status,
            severity,
            1,
            1,
            coverage,
            timer.summary(),
            issues,
            (dom_fallback or {}).get("source_path") or fetch_source,
            slim_payload,
        )

    async def _audit_comment(
        self,
        page,
        *,
        url: str,
        limit: int,
        platform_context: dict[str, Any] | None = None,
        comment_items: list[dict[str, Any]] | None = None,
    ) -> EngineAuditRecord:
        note_id = url.rstrip("/").split("/")[-1].split("?")[0]
        timer = PerfTimer()
        with timer.stage("api"):
            result = await XhsCommentProbe().fetch_comments_result(
            page,
            canonical_url=url,
            platform_content_id=note_id,
            platform_context=platform_context or {},
            limit=limit,
        )
        timer.set_items(len(result.comments))
        comments = [item.model_dump(mode="json") for item in result.comments]
        diagnostics = dict(result.diagnostics or {})
        source_path = diagnostics.get("source_path") or diagnostics.get("source") or "missing"
        if comment_items is not None:
            comment_items.extend(
                serialize_comment_item(comment, index=index, source_path=source_path)
                for index, comment in enumerate(comments, start=1)
            )
        if result.surface_status == "missing_xsec_context":
            severity = AuditSeverity.P2_MAJOR
        elif result.surface_status in {"ok", "true_empty_comments"}:
            severity = AuditSeverity.P4_INFO
        else:
            severity = AuditSeverity.P2_MAJOR
        issues = []
        if severity != AuditSeverity.P4_INFO:
            issues.append(
                EngineAuditIssue(
                    severity,
                    "xhs.note.comments",
                    "comment",
                    result.error_code or result.surface_status,
                    result.message or result.surface_status,
                    result.diagnostics,
                )
            )
        diagnostics["selected_url_redacted"] = redact_url(url)
        return EngineAuditRecord(
            "xhs.note.comments",
            "comment",
            result.surface_status,
            severity,
            len(comments),
            len(comments),
            field_coverage(comments, ["platform_comment_id", "body_text", "author_name", "like_count"]),
            timer.summary(),
            issues,
            diagnostics.get("source_path") or diagnostics.get("source"),
            {
                "diagnostics": diagnostics,
                "api_page_count": diagnostics.get("api_page_count") or diagnostics.get("page_count"),
                "surface_status": result.surface_status,
            },
        )

    async def _audit_creator(self, page, *, creator_url: str, limit: int) -> EngineAuditRecord:
        timer = PerfTimer()
        try:
            result = await XhsCreatorConnector().fetch_latest(page, creator_profile_url=creator_url, limit=limit)
        except Exception as exc:
            return EngineAuditRecord(
                "xhs.creator.posted_notes",
                "creator",
                "failed",
                AuditSeverity.P2_MAJOR,
                perf=timer.summary(),
                issues=[EngineAuditIssue(AuditSeverity.P2_MAJOR, "xhs.creator.posted_notes", "creator", "creator_surface_unavailable", str(exc)[:300])],
                source_path="creator_probe",
            )
        timer.set_items(len(result.items))
        items = [item.to_candidate(feed_position=index).model_dump(mode="json") for index, item in enumerate(result.items, 1)]
        return EngineAuditRecord(
            "xhs.creator.posted_notes",
            "creator",
            "ok",
            AuditSeverity.P4_INFO,
            len(items),
            len(items),
            field_coverage(items, ["platform_content_id", "canonical_url", "title_or_summary", "cover_url"]),
            timer.summary(),
            [],
            "creator_user_posted",
            {"creator_display_name": result.creator_display_name},
        )
