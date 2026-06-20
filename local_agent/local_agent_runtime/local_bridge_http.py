from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


def build_local_bridge_handler(service):
    session_status_pattern = re.compile(r"^/bridge/accounts/([^/]+)/session-status$")
    revalidate_pattern = re.compile(r"^/bridge/accounts/([^/]+)/revalidate$")
    content_detail_pattern = re.compile(r"^/api/local/contents/(\d+)$")
    content_status_pattern = re.compile(r"^/api/local/contents/(\d+)/status$")
    task_detail_pattern = re.compile(r"^/api/local/tasks/(\d+)$")
    task_action_pattern = re.compile(r"^/api/local/tasks/(\d+)/(run|viewed|pause|resume|cancel)$")
    acquisition_pattern = re.compile(r"^/api/local/contents/(\d+)/acquisition-check$")
    detail_fetch_pattern = re.compile(r"^/api/local/contents/(\d+)/detail-fetch$")
    material_pattern = re.compile(r"^/api/local/contents/(\d+)/material$")

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            if not is_trusted_origin(self.headers.get("Origin"), self.headers.get("Host")):
                self._write_json(403, {"detail": "cross-origin request rejected"})
                return
            self.send_response(204)
            self._set_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._write_static("index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/styles.css":
                self._write_static("styles.css", "text/css; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._write_static("app.js", "text/javascript; charset=utf-8")
                return
            if parsed.path == "/healthz":
                self._write_json(200, {"status": "ok"})
                return
            if parsed.path == "/bridge/agents/discover":
                self._write_json(
                    200,
                    {
                        "items": [
                            {
                                "device_name": service.config.device_name,
                                "machine_fingerprint": service.config.machine_fingerprint,
                                "agent_id": service.config.agent_id,
                                "center_url": service.config.center_base_url,
                                "bridge_url": f"http://{service.config.local_bridge_host}:{service.config.local_bridge_port}",
                                "bridge_port": service.config.local_bridge_port,
                                "status": "online",
                            }
                        ]
                    },
                )
                return

            token = _extract_token(
                self.headers.get("Authorization"),
                parse_qs(parsed.query).get("token", [None])[0],
                self.headers.get("Cookie"),
            )
            if not service.authorize_request(
                token=token,
                origin=self.headers.get("Origin"),
                host=self.headers.get("Host"),
                fetch_site=self.headers.get("Sec-Fetch-Site"),
            ):
                self._write_json(401, {"detail": "invalid token or origin"})
                return

            query = parse_qs(parsed.query)
            if parsed.path == "/api/local/media":
                try:
                    media_url = query.get("url", [None])[0]
                    data, content_type = fetch_allowed_image(media_url)
                    self._write_bytes(200, data, content_type)
                except ValueError as exc:
                    self._write_json(400, {"detail": str(exc)})
                except httpx.HTTPError as exc:
                    self._write_json(502, {"detail": f"image fetch failed: {exc}"})
                return
            if parsed.path == "/api/local/contents":
                try:
                    self._write_json(200, service.list_contents(query))
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = content_detail_pattern.match(parsed.path)
            if match:
                try:
                    item = service.get_content_detail(int(match.group(1)))
                    self._write_json(200 if item else 404, item or {"detail": "content not found"})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/tasks":
                try:
                    self._write_json(200, service.list_tasks(query))
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/central-session":
                try:
                    self._write_json(200, service.central_session_status())
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = task_detail_pattern.match(parsed.path)
            if match:
                try:
                    item = service.get_task(int(match.group(1)))
                    self._write_json(200 if item else 404, item or {"detail": "task not found"})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return

            match = session_status_pattern.match(parsed.path)
            if not match:
                self._write_json(404, {"detail": "not found"})
                return
            account_id = match.group(1)
            query = parse_qs(parsed.query)
            cdp_port = _query_int(query.get("cdp_port", [None])[0])
            try:
                result = service.probe_account_session(account_id, cdp_port=cdp_port)
                self._write_json(200, result)
            except Exception as exc:
                self._write_json(500, {"detail": str(exc)})

        def do_POST(self):
            parsed = urlparse(self.path)
            token = _extract_token(
                self.headers.get("Authorization"),
                parse_qs(parsed.query).get("token", [None])[0],
                self.headers.get("Cookie"),
            )
            if not service.authorize_request(
                token=token,
                origin=self.headers.get("Origin"),
                host=self.headers.get("Host"),
                fetch_site=self.headers.get("Sec-Fetch-Site"),
            ):
                self._write_json(401, {"detail": "invalid token or origin"})
                return

            if parsed.path == "/bridge/session":
                self.send_response(204)
                self._set_cors_headers()
                self.send_header(
                    "Set-Cookie",
                    f"local_bridge_session={token}; HttpOnly; SameSite=Strict; Path=/",
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            body = self._read_json_body()
            if parsed.path == "/api/local/central-session/login":
                try:
                    self._write_json(200, service.central_session_login(body))
                except ValueError as exc:
                    self._write_json(400, {"detail": str(exc)})
                except PermissionError as exc:
                    self._write_json(403, {"detail": str(exc)})
                except httpx.HTTPStatusError as exc:
                    self._write_json(exc.response.status_code, {"detail": "central login failed"})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/central-session/logout":
                try:
                    self._write_json(200, service.central_session_logout())
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/materials/retry":
                try:
                    self._write_json(200, service.retry_material_library())
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/contents/batch-status":
                try:
                    self._write_json(200, service.batch_update_content_status(body))
                except ValueError as exc:
                    self._write_json(400, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = content_status_pattern.match(parsed.path)
            if match:
                try:
                    self._write_json(
                        200,
                        service.update_content_status(int(match.group(1)), body),
                    )
                except ValueError as exc:
                    self._write_json(404, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = acquisition_pattern.match(parsed.path)
            if match:
                try:
                    self._write_json(
                        202,
                        service.submit_acquisition_check(int(match.group(1)), body),
                    )
                except ValueError as exc:
                    self._write_json(404, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = detail_fetch_pattern.match(parsed.path)
            if match:
                try:
                    self._write_json(
                        202,
                        service.submit_detail_fetch(int(match.group(1))),
                    )
                except ValueError as exc:
                    self._write_json(404, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = material_pattern.match(parsed.path)
            if match:
                try:
                    result = service.add_to_material_library(int(match.group(1)), body)
                    self._write_json(200 if result.get("status") == "synced" else 202, result)
                except ValueError as exc:
                    self._write_json(404, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/search":
                try:
                    self._write_json(202, service.submit_search(body))
                except ValueError as exc:
                    self._write_json(400, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/api/local/tasks":
                try:
                    self._write_json(202, service.submit_collection_task(body))
                except ValueError as exc:
                    self._write_json(400, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            match = task_action_pattern.match(parsed.path)
            if match:
                task_id = int(match.group(1))
                action = match.group(2)
                try:
                    result = (
                        service.run_collection_task(task_id)
                        if action == "run"
                        else service.update_task_action(task_id, action)
                    )
                    self._write_json(202 if action == "run" else 200, result)
                except ValueError as exc:
                    self._write_json(404, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(503, {"detail": str(exc)})
                return
            if parsed.path == "/bridge/chrome/start":
                try:
                    result = service.launch_chrome(body)
                    self._write_json(200, result)
                except ValueError as exc:
                    self._write_json(400, {"detail": str(exc)})
                except Exception as exc:
                    self._write_json(500, {"detail": str(exc)})
                return

            match = revalidate_pattern.match(parsed.path)
            if match:
                account_id = match.group(1)
                cdp_port = body.get("cdp_port")
                if cdp_port is not None:
                    cdp_port = int(cdp_port)
                cdp_url = str(body.get("cdp_url") or "").strip() or None
                try:
                    result = service.revalidate_account_session(
                        account_id,
                        cdp_port=cdp_port,
                        cdp_url=cdp_url,
                    )
                    self._write_json(200, result)
                except Exception as exc:
                    self._write_json(500, {"detail": str(exc)})
                return

            self._write_json(404, {"detail": "not found"})

        def log_message(self, format: str, *args):  # noqa: A003
            return

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            payload = self.rfile.read(length).decode("utf-8")
            if not payload:
                return {}
            return json.loads(payload)

        def _write_json(self, status: int, payload: dict[str, Any]):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write_static(self, filename: str, content_type: str):
            path = service.web_root / filename
            if not path.exists():
                self._write_json(404, {"detail": "asset not found"})
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write_bytes(self, status: int, data: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _set_cors_headers(self):
            origin = self.headers.get("Origin")
            if origin and is_trusted_origin(origin, self.headers.get("Host")):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    return Handler


def fetch_allowed_image(url: str | None) -> tuple[bytes, str]:
    parsed = urlparse(str(url or "").strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        hostname == "xhscdn.com" or hostname.endswith(".xhscdn.com")
    ):
        raise ValueError("unsupported image host")
    secure_url = parsed._replace(scheme="https").geturl()
    response = httpx.get(
        secure_url,
        headers={
            "Referer": "https://www.xiaohongshu.com/",
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    )
    response.raise_for_status()
    content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        raise ValueError("upstream response is not an image")
    if len(response.content) > 20 * 1024 * 1024:
        raise ValueError("image exceeds size limit")
    return response.content, content_type


def _extract_token(
    auth_header: str | None,
    query_token: str | None,
    cookie_header: str | None,
) -> str | None:
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    if query_token:
        return query_token
    for item in (cookie_header or "").split(";"):
        key, separator, value = item.strip().partition("=")
        if separator and key == "local_bridge_session":
            return value
    return None


def is_trusted_origin(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        return False
    request_host = (host or "").lower()
    expected_port = request_host.rsplit(":", 1)[-1] if ":" in request_host else None
    if parsed.port and expected_port and str(parsed.port) == expected_port:
        return True
    return parsed.port == 5173
