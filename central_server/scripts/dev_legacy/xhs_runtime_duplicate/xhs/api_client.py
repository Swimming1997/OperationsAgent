from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import httpx
from playwright.async_api import BrowserContext


XHS_API_HOST = "https://edith.xiaohongshu.com"
XHS_WEB_HOST = "https://www.xiaohongshu.com"


class XhsApiError(RuntimeError):
    pass


class XhsApiUnavailable(XhsApiError):
    pass


def _build_query_string(params: dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        value_str = str(value) if value is not None else ""
        parts.append(f"{key}={quote(value_str, safe=',')}")
    return "&".join(parts)


def _trace_id() -> str:
    alphabet = "abcdef0123456789"
    return "".join(random.choice(alphabet) for _ in range(16))


def _build_sign_string(uri: str, data: dict[str, Any] | None = None, method: str = "POST") -> str:
    if method.upper() == "POST":
        return uri + (json.dumps(data or {}, separators=(",", ":"), ensure_ascii=False) if data is not None else "")
    if not data:
        return uri
    return f"{uri}?{_build_query_string(data)}"


def _patch_xhshow_get_hash() -> None:
    from xhshow.core.crypto import CryptoProcessor  # type: ignore

    if getattr(CryptoProcessor.build_payload_array, "_amiracle_xhs_patched", False):
        return
    original_build = CryptoProcessor.build_payload_array

    def patched_build(self, hex_parameter, a1_value, app_identifier="xhs-pc-web", string_param="", timestamp=None, sign_state=None):
        payload = original_build(self, hex_parameter, a1_value, app_identifier, string_param, timestamp, sign_state)
        if "{" not in string_param:
            correct_md5_hex = hashlib.md5(string_param.encode("utf-8")).hexdigest()
            correct_md5_bytes = [int(correct_md5_hex[i : i + 2], 16) for i in range(0, 32, 2)]
            seed_byte = payload[4]
            ts_bytes = payload[8:16]
            correct_a3_hash = self._custom_hash_v2(list(ts_bytes) + correct_md5_bytes)
            for index in range(16):
                payload[128 + index] = correct_a3_hash[index] ^ seed_byte
        return payload

    patched_build._amiracle_xhs_patched = True
    CryptoProcessor.build_payload_array = patched_build


async def browser_context_cookie_header(context: BrowserContext) -> str:
    cookies = await context.cookies(urls=[XHS_WEB_HOST, XHS_API_HOST])
    return ";".join(f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies if cookie.get("name"))


def sign_xhs_headers(*, uri: str, data: dict[str, Any], cookie_str: str, method: str) -> dict[str, str]:
    try:
        _patch_xhshow_get_hash()
        from xhshow import Xhshow  # type: ignore
    except Exception as exc:
        raise XhsApiUnavailable("xhshow is not installed; signed XHS API is unavailable") from exc

    signer = Xhshow()
    method = method.upper()
    if method == "POST":
        signed = signer.sign_headers_post(uri=uri, payload=data, cookies=cookie_str)
        return {
            "X-S": signed.get("x-s", ""),
            "X-T": signed.get("x-t", ""),
            "x-S-Common": signed.get("x-s-common", ""),
            "X-B3-Traceid": signed.get("x-b3-traceid", _trace_id()),
        }
    if method == "GET":
        content_string = _build_sign_string(uri, data, method)
        cookie_dict = signer._parse_cookies(cookie_str)
        ts = time.time()
        a1_value = cookie_dict.get("a1", "")
        d_value = hashlib.md5(content_string.encode("utf-8")).hexdigest()
        payload_array = signer.crypto_processor.build_payload_array(
            d_value,
            a1_value,
            "xhs-pc-web",
            content_string,
            ts,
        )
        xor_result = signer.crypto_processor.bit_ops.xor_transform_array(payload_array)
        config = signer.config
        x3_b64 = signer.crypto_processor.b64encoder.encode_x3(xor_result[: config.PAYLOAD_LENGTH])
        sig_data = config.SIGNATURE_DATA_TEMPLATE.copy()
        sig_data["x3"] = config.X3_PREFIX + x3_b64
        x_s = config.XYS_PREFIX + signer.crypto_processor.b64encoder.encode(json.dumps(sig_data, separators=(",", ":"), ensure_ascii=False))
        return {
            "X-S": x_s,
            "X-T": str(signer.get_x_t(ts)),
            "x-S-Common": signer.sign_xs_common(cookie_dict),
            "X-B3-Traceid": signer.get_b3_trace_id(),
        }
    raise ValueError(f"unsupported method: {method}")


@dataclass
class XhsApiClient:
    cookie_str: str
    timeout: float = 30
    signer: Callable[..., dict[str, str]] = sign_xhs_headers

    def _base_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/json;charset=UTF-8",
            "origin": XHS_WEB_HOST,
            "pragma": "no-cache",
            "referer": f"{XHS_WEB_HOST}/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Cookie": self.cookie_str,
        }

    async def _request(self, method: str, uri: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        sign_data = params if params is not None else payload
        if sign_data is None:
            sign_data = {}
        headers = self._base_headers()
        headers.update(self.signer(uri=uri, data=sign_data, cookie_str=self.cookie_str, method=method))
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if method.upper() == "GET":
                url = f"{XHS_API_HOST}{uri}"
                if params:
                    url = f"{url}?{_build_query_string(params)}"
                response = await client.get(url, headers=headers)
            else:
                response = await client.post(
                    f"{XHS_API_HOST}{uri}",
                    data=json.dumps(payload or {}, separators=(",", ":"), ensure_ascii=False),
                    headers=headers,
                )
        response.raise_for_status()
        body = response.json()
        if body.get("success"):
            return body.get("data") or {}
        raise XhsApiError(body.get("msg") or response.text)

    async def get_note_by_id(self, *, note_id: str, xsec_source: str, xsec_token: str) -> dict[str, Any]:
        data = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
            "xsec_source": xsec_source or "pc_search",
            "xsec_token": xsec_token,
        }
        result = await self._request("POST", "/api/sns/web/v1/feed", payload=data)
        items = result.get("items") or []
        if not items:
            return {}
        note_card = items[0].get("note_card") or {}
        note_card.setdefault("note_id", note_id)
        note_card.setdefault("xsec_token", xsec_token)
        note_card.setdefault("xsec_source", xsec_source or "pc_search")
        return note_card

    async def get_note_comments_page(self, *, note_id: str, xsec_token: str, cursor: str = "") -> dict[str, Any]:
        params = {
            "note_id": note_id,
            "cursor": cursor,
            "top_comment_id": "",
            "image_formats": "jpg,webp,avif",
            "xsec_token": xsec_token,
        }
        return await self._request("GET", "/api/sns/web/v2/comment/page", params=params)

    async def get_note_comments(self, *, note_id: str, xsec_token: str, limit: int = 20) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        cursor = ""
        page_count = 0
        has_more = True
        while has_more and len(comments) < limit:
            page = await self.get_note_comments_page(note_id=note_id, xsec_token=xsec_token, cursor=cursor)
            page_count += 1
            page_comments = page.get("comments") or []
            comments.extend(page_comments[: max(0, limit - len(comments))])
            has_more = bool(page.get("has_more")) and bool(page_comments)
            cursor = page.get("cursor") or ""
            if not cursor and has_more:
                break
        return comments[:limit], {"source": "api", "page_count": page_count, "has_more": has_more, "cursor": cursor}
