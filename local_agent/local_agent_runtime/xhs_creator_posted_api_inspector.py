from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from local_agent_runtime.connectors.xhs.creator import parse_xhs_creator_context
from local_agent_runtime.connectors.xhs.creator import parse_user_posted_response
from local_agent_runtime.sessions.xhs_browser_session import XhsBrowserSessionProvider
from local_agent_runtime.enums import SessionStatus


class XhsCreatorPostedApiInspector:
    def __init__(self, *, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url

    async def run(self, *, creator_url: str, limit: int = 20) -> dict[str, Any]:
        context = parse_xhs_creator_context(creator_url)
        params = {
            "num": str(limit),
            "cursor": "",
            "user_id": context.creator_platform_id,
            "image_formats": "jpg,webp,avif",
            "xsec_token": context.xsec_token,
            "xsec_source": context.xsec_source,
        }
        session = await XhsBrowserSessionProvider().acquire(session_meta={"cdp_url": self.cdp_url})
        if session.status != SessionStatus.READY:
            await session.close()
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "creator_context": context.to_payload(),
                "request_params": params,
                "request_sent": False,
            }
        try:
            page = session.page
            assert page is not None
            captured_payloads: list[dict[str, Any]] = []

            async def capture_user_posted(response):
                if "/api/sns/web/v1/user_posted" not in response.url:
                    return
                try:
                    payload = await response.json()
                    if isinstance(payload, dict):
                        notes, meta = parse_user_posted_response(payload)
                        captured_payloads.append(
                            {
                                "url": response.url,
                                "http_status": response.status,
                                "meta": meta,
                                "notes_count": len(notes),
                                "payload_prefix": json_safe_prefix(payload),
                            }
                        )
                except Exception:
                    try:
                        captured_payloads.append({"url": response.url, "http_status": response.status, "text_prefix": (await response.text())[:1000]})
                    except Exception:
                        pass

            def on_response(response):
                import asyncio

                asyncio.create_task(capture_user_posted(response))

            page.on("response", on_response)
            await page.goto(creator_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            for _ in range(3):
                await page.mouse.wheel(0, 1800)
                await page.wait_for_timeout(1500)
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass
            result = await page.evaluate(
                """
                async ({params}) => {
                  const query = new URLSearchParams(params);
                  const url = `/api/sns/web/v1/user_posted?${query.toString()}`;
                  const out = {
                    request_sent: false,
                    request_url: url,
                    request_params: params,
                    http_status: null,
                    response_headers: {},
                    raw_text_prefix: "",
                    json_parse_ok: false,
                    json_top_level_keys: [],
                    has_notes: false,
                    notes_count: 0,
                    has_has_more: false,
                    has_cursor: false,
                    error_fields: {},
                    response_summary: null
                  };
                  try {
                    const response = await fetch(url, {
                      method: "GET",
                      credentials: "include",
                      headers: {"accept": "application/json, text/plain, */*"}
                    });
                    out.request_sent = true;
                    out.http_status = response.status;
                    response.headers.forEach((value, key) => out.response_headers[key] = value);
                    const text = await response.text();
                    out.raw_text_prefix = text.slice(0, 3000);
                    try {
                      const json = JSON.parse(text);
                      out.json_parse_ok = true;
                      out.json_top_level_keys = Object.keys(json);
                      out.has_notes = Array.isArray(json.notes);
                      out.notes_count = Array.isArray(json.notes) ? json.notes.length : 0;
                      out.has_has_more = Object.prototype.hasOwnProperty.call(json, "has_more");
                      out.has_cursor = Object.prototype.hasOwnProperty.call(json, "cursor");
                      out.error_fields = {
                        code: json.code ?? json.error_code ?? json.err_code ?? null,
                        msg: json.msg ?? json.message ?? json.error_msg ?? null,
                        success: json.success ?? null
                      };
                      out.response_summary = JSON.stringify(json).slice(0, 3000);
                    } catch (e) {
                      out.response_summary = `JSON parse failed: ${String(e)}`;
                    }
                    return out;
                  } catch (e) {
                    out.request_error = String(e);
                    return out;
                  }
                }
                """,
                {"params": params},
            )
            return {
                "session_status": session.status.value,
                "session_message": session.message,
                "creator_context": context.to_payload(),
                "request_params": params,
                "request_query": urlencode(params),
                "signed_page_request_count": len(captured_payloads),
                "signed_page_requests": captured_payloads,
                **result,
                "items_seen_zero_reason": self._items_seen_zero_reason(result),
            }
        finally:
            await session.close()

    def _items_seen_zero_reason(self, result: dict[str, Any]) -> str:
        if not result.get("request_sent"):
            return "request_not_sent"
        if result.get("http_status") != 200:
            return "http_non_200"
        if not result.get("json_parse_ok"):
            return "response_not_json"
        if not result.get("has_notes"):
            return "response_missing_notes"
        if result.get("notes_count", 0) == 0:
            return "notes_empty"
        return "notes_present"


def json_safe_prefix(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)[:2000]
