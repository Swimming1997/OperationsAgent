from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
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


_SELF_INFO_NESTED_KEYS = ("basic_info", "user", "profile", "user_info", "result")
_SELF_INFO_SENSITIVE_KEYS = frozenset(
    {
        "cookie",
        "cookies",
        "authorization",
        "headers",
        "x-s",
        "x-t",
        "x-s-common",
        "xsec_token",
        "xsec_source",
    }
)
_NICKNAME_KEYS = ("nickname", "nick_name", "name", "user_name", "display_name")
_USER_ID_KEYS = ("user_id", "userid", "userId")
_USER_ID_FALLBACK_KEYS = ("id",)
_RED_ID_KEYS = ("red_id", "redId", "redid")
_HOME_URL_KEYS = ("home_url", "profile_url", "user_link", "user_url", "share_link", "web_url")
_AVATAR_KEYS = ("avatar_url", "avatar", "image", "images")


def _looks_like_xhs_internal_user_id(value: str) -> bool:
    text = value.strip()
    return len(text) == 24 and all(ch in "0123456789abcdef" for ch in text.lower())


def _self_info_source_dicts(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    sources: list[tuple[str, dict[str, Any]]] = [("data", data)]
    for key in _SELF_INFO_NESTED_KEYS:
        nested = data.get(key)
        if isinstance(nested, dict):
            sources.append((f"data.{key}", nested))
    return sources


def _self_info_field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix != "data" else f"data.{key}"


def _first_nonempty_string(
    sources: list[tuple[str, dict[str, Any]]],
    keys: tuple[str, ...],
) -> tuple[str | None, str | None]:
    for prefix, src in sources:
        for key in keys:
            value = src.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text, _self_info_field_path(prefix, key)
    return None, None


def _extract_avatar_url(sources: list[tuple[str, dict[str, Any]]]) -> tuple[str | None, str | None]:
    for prefix, src in sources:
        for key in _AVATAR_KEYS:
            value = src.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), _self_info_field_path(prefix, key)
            if isinstance(value, dict):
                nested_url = value.get("url") or value.get("url_default") or value.get("link")
                if nested_url and str(nested_url).strip():
                    return str(nested_url).strip(), f"{_self_info_field_path(prefix, key)}.url"
    return None, None


@dataclass
class SelfInfoExtractResult:
    nickname: str | None = None
    user_id: str | None = None
    red_id: str | None = None
    home_url: str | None = None
    avatar_url: str | None = None
    field_sources: dict[str, str] = field(default_factory=dict)


def extract_self_info_result(data: dict[str, Any] | None) -> SelfInfoExtractResult:
    if not isinstance(data, dict):
        return SelfInfoExtractResult()
    sources = _self_info_source_dicts(data)
    nickname, nickname_src = _first_nonempty_string(sources, _NICKNAME_KEYS)
    red_id, red_id_src = _first_nonempty_string(sources, _RED_ID_KEYS)
    user_id, user_id_src = _first_nonempty_string(sources, _USER_ID_KEYS)
    if not user_id:
        for prefix, src in sources:
            for key in _USER_ID_FALLBACK_KEYS:
                value = src.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if text and _looks_like_xhs_internal_user_id(text):
                    user_id = text
                    user_id_src = _self_info_field_path(prefix, key)
                    break
            if user_id:
                break
    home_url, home_url_src = _first_nonempty_string(sources, _HOME_URL_KEYS)
    avatar_url, avatar_src = _extract_avatar_url(sources)
    field_sources: dict[str, str] = {}
    if nickname_src:
        field_sources["nickname"] = nickname_src
    if user_id_src:
        field_sources["user_id"] = user_id_src
    if red_id_src:
        field_sources["red_id"] = red_id_src
    if home_url_src:
        field_sources["home_url"] = home_url_src
    if avatar_src:
        field_sources["avatar_url"] = avatar_src
    if user_id and not home_url:
        home_url = f"{XHS_WEB_HOST}/user/profile/{user_id}"
        field_sources["home_url"] = "derived_from_user_id"
    return SelfInfoExtractResult(
        nickname=nickname,
        user_id=user_id,
        red_id=red_id,
        home_url=home_url,
        avatar_url=avatar_url,
        field_sources=field_sources,
    )


def extract_self_info_fields(data: dict[str, Any] | None) -> dict[str, Any]:
    result = extract_self_info_result(data)
    return {
        "nickname": result.nickname,
        "user_id": result.user_id,
        "red_id": result.red_id,
        "home_url": result.home_url,
        "avatar_url": result.avatar_url,
    }


def _self_info_fmt(value: Any) -> str:
    if value is None:
        return "missing"
    text = str(value).strip()
    return text or "missing"


def build_self_info_account_summary(
    *,
    logged_in: bool,
    status: str,
    fields: dict[str, Any] | None = None,
    extract: SelfInfoExtractResult | None = None,
    source: str = "signed_api_selfinfo",
) -> dict[str, Any]:
    if extract is None:
        extract = extract_self_info_result(fields or {})
    if not logged_in:
        login_status = "failed"
    elif status == "ok":
        login_status = "ok"
    else:
        login_status = "partial"

    if extract.user_id:
        stable_user_key = extract.user_id
        stable_user_key_source = "user_id"
    elif extract.red_id:
        stable_user_key = extract.red_id
        stable_user_key_source = "red_id"
    else:
        stable_user_key = "missing"
        stable_user_key_source = "missing"

    missing_fields: list[str] = []
    missing_reasons: dict[str, str] = {}
    if not extract.nickname:
        missing_fields.append("nickname")
        missing_reasons["nickname"] = "selfinfo_response_no_nickname_field"
    if not extract.red_id:
        missing_fields.append("red_id")
        missing_reasons["red_id"] = "selfinfo_response_no_red_id_field"
    if not extract.user_id:
        missing_fields.append("user_id")
        missing_reasons["user_id"] = "selfinfo_response_no_user_id_field"
    if not extract.home_url:
        missing_fields.append("home_url")
        if not extract.user_id:
            missing_reasons["home_url"] = "cannot_derive_without_user_id"
        else:
            missing_reasons["home_url"] = "selfinfo_response_no_home_url_field"
    if not extract.avatar_url:
        missing_fields.append("avatar_url")
        missing_reasons["avatar_url"] = "selfinfo_response_no_avatar_field"

    home_url_source = extract.field_sources.get("home_url", "missing")
    if home_url_source == "derived_from_user_id":
        home_url_source_value = "derived_from_user_id"
    elif extract.home_url:
        home_url_source_value = "api"
    else:
        home_url_source_value = "missing"

    field_sources = {
        "login_status": "self_info",
        "nickname": extract.field_sources.get("nickname", "missing"),
        "user_id": extract.field_sources.get("user_id", "missing"),
        "red_id": extract.field_sources.get("red_id", "missing"),
        "stable_user_key": stable_user_key_source,
        "home_url": home_url_source_value,
        "avatar_url": extract.field_sources.get("avatar_url", "missing"),
        "source": "api",
    }

    return {
        "login_status": login_status,
        "nickname": _self_info_fmt(extract.nickname),
        "user_id": _self_info_fmt(extract.user_id),
        "red_id": _self_info_fmt(extract.red_id),
        "stable_user_key": _self_info_fmt(stable_user_key),
        "stable_user_key_source": stable_user_key_source,
        "home_url": _self_info_fmt(extract.home_url),
        "home_url_source": home_url_source_value,
        "avatar_url": _self_info_fmt(extract.avatar_url),
        "missing_fields": missing_fields,
        "missing_reasons": missing_reasons,
        "source": source,
        "field_sources": field_sources,
    }


def classify_self_info_severity(
    *,
    logged_in: bool,
    summary: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
) -> AuditSeverity:
    from local_agent_runtime.audit.levels import AuditSeverity

    if not logged_in:
        return AuditSeverity.P1_BLOCKER
    if summary is None:
        summary = build_self_info_account_summary(logged_in=True, status="partial", fields=fields or {})
    missing = summary.get("missing_fields") or []
    if "nickname" in missing or "red_id" in missing:
        return AuditSeverity.P2_MAJOR
    if "user_id" in missing or "home_url" in missing:
        return AuditSeverity.P2_MAJOR
    if "avatar_url" in missing:
        return AuditSeverity.P3_MINOR
    return AuditSeverity.P4_INFO


def format_self_info_terminal_lines(*, status: str, account_summary: dict[str, Any]) -> list[str]:
    login_status = account_summary.get("login_status", status)
    nickname = account_summary.get("nickname", "missing")
    red_id = account_summary.get("red_id", "missing")
    user_id = account_summary.get("user_id", "missing")
    home_url = account_summary.get("home_url", "missing")
    stable_user_key = account_summary.get("stable_user_key", "missing")
    stable_user_key_source = account_summary.get("stable_user_key_source", "missing")
    stable_display = f"{stable_user_key}({stable_user_key_source})" if stable_user_key != "missing" else "missing"
    lines = [
        (
            f"self_info: {login_status}, nickname={nickname}, red_id={red_id}, "
            f"user_id={user_id}, home_url={home_url}, stable_user_key={stable_display}"
        )
    ]
    missing = account_summary.get("missing_fields") or []
    if missing:
        lines.append(f"missing_fields: {', '.join(missing)}")
    severity = classify_self_info_severity(
        logged_in=login_status != "failed",
        summary=account_summary,
    )
    lines.append(f"highest_severity: {severity.value}")
    return lines


def format_self_info_terminal_line(*, status: str, account_summary: dict[str, Any]) -> str:
    return "\n".join(format_self_info_terminal_lines(status=status, account_summary=account_summary))


def sanitize_self_info_raw_fields(data: Any) -> Any:
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if str(key).lower() in _SELF_INFO_SENSITIVE_KEYS:
                continue
            sanitized[key] = sanitize_self_info_raw_fields(value)
        return sanitized
    if isinstance(data, list):
        return [sanitize_self_info_raw_fields(item) for item in data[:20]]
    if isinstance(data, str):
        return data if len(data) <= 500 else data[:500] + "..."
    if isinstance(data, (int, float, bool)) or data is None:
        return data
    return type(data).__name__


def write_self_info_raw_fields_debug(*, project_root: Path, run_id: str, data: dict[str, Any]) -> Path:
    output_dir = project_root / "logs" / "audit" / "xhs_engine" / run_id[:8]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"self_info_raw_fields_{run_id}.json"
    payload = {"run_id": run_id, "data": sanitize_self_info_raw_fields(data)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
        effective_source = xsec_source or "pc_search"
        data = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
            "xsec_source": effective_source,
            "xsec_token": xsec_token,
        }
        result = await self._request("POST", "/api/sns/web/v1/feed", payload=data)
        items = result.get("items") or []
        if not items:
            return {}
        note_card = items[0].get("note_card") or {}
        note_card.setdefault("note_id", note_id)
        note_card.setdefault("xsec_token", xsec_token)
        note_card.setdefault("xsec_source", effective_source)
        return note_card

    async def search_notes(
        self,
        *,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        search_id: str | None = None,
        sort: str = "general",
        note_type: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": search_id or "".join(random.choice("abcdef0123456789") for _ in range(16)),
            "sort": sort,
            "note_type": note_type,
        }
        return await self._request("POST", "/api/sns/web/v1/search/notes", payload=payload)

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

    async def query_self(self) -> dict[str, Any]:
        return await self._request("GET", "/api/sns/web/v1/user/selfinfo", params={})

    async def pong(self) -> tuple[bool, dict[str, Any]]:
        try:
            data = await self.query_self()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body_text = exc.response.text[:300]
            if status in {401, 403}:
                code = "login_required"
            elif status == 461 or "verify" in body_text.lower() or "验证" in body_text:
                code = "manual_verify_required"
            else:
                code = "api_http_failed"
            return (
                False,
                {
                    "error_code": code,
                    "http_status": status,
                    "message": f"self_info HTTP {status}",
                },
            )
        except XhsApiUnavailable as exc:
            return False, {"error_code": "api_signature_failed", "message": str(exc)}
        except XhsApiError as exc:
            message = str(exc)
            lowered = message.lower()
            if "login" in lowered or "登录" in message or "未登录" in message:
                code = "login_required"
            elif "verify" in lowered or "验证" in message or "滑块" in message:
                code = "manual_verify_required"
            else:
                code = "api_http_failed"
            return False, {"error_code": code, "message": message[:300]}
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if "login" in lowered or "登录" in message:
                code = "login_required"
            elif "verify" in lowered or "验证" in message:
                code = "manual_verify_required"
            else:
                code = "api_http_failed"
            return False, {"error_code": code, "message": message[:300]}
        fields = extract_self_info_fields(data if isinstance(data, dict) else {})
        extract = extract_self_info_result(data if isinstance(data, dict) else {})
        merged = {**(data if isinstance(data, dict) else {}), **fields}
        logged_in = bool(extract.nickname or extract.user_id)
        if not logged_in:
            return False, {
                **merged,
                "error_code": "login_required",
                "message": "self_info 未返回 nickname 或 user_id，当前会话未登录或资料不可用",
            }
        return True, merged
