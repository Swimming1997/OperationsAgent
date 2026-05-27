from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

from local_agent_runtime.account_login_executor import AccountLoginExecutor
from local_agent_runtime.chrome_launcher import launch_managed_chrome
from local_agent_runtime.runtime import AgentRuntimeConfig


@dataclass(frozen=True)
class LocalBridgeConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 18765
    token: str | None = None


class LocalBridgeService:
    def __init__(self, *, config: AgentRuntimeConfig, loop: asyncio.AbstractEventLoop):
        self.config = config
        self.loop = loop
        self.project_root = Path(config.project_root or Path.cwd()).resolve()
        self._probe_executor = AccountLoginExecutor(project_root=self.project_root, client=_NoopClient())
        # account_id -> cdp_url，由本进程 chrome/start 或前端传入端口写入
        self._runtime_account_cdp: dict[str, str] = {}

    def require_token(self, token: str | None) -> bool:
        expected = self.config.local_bridge_token
        if not expected:
            return True
        return bool(token and token == expected)

    def launch_chrome(self, payload: dict[str, Any]) -> dict[str, Any]:
        account_id = str(payload.get("account_id") or "").strip() or None
        profile_key = str(payload.get("profile_key") or "").strip()
        cdp_port = payload.get("port")
        url = str(payload.get("url") or "https://www.xiaohongshu.com/explore")
        if not profile_key and account_id:
            profile_key = account_id
        if not profile_key:
            raise ValueError("profile_key is required")
        if cdp_port is None:
            cdp_url = str(payload.get("cdp_url") or "").strip()
            cdp_port = _extract_port(cdp_url) if cdp_url else None
        if cdp_port is None:
            raise ValueError("port is required")
        port_number = int(cdp_port)
        if port_number < 1000 or port_number > 65535:
            raise ValueError("port must be between 1000 and 65535")
        fresh_profile = bool(payload.get("fresh_profile"))
        profile_dir, process = launch_managed_chrome(
            project_root=self.project_root,
            profile_key=profile_key,
            cdp_port=port_number,
            url=url,
            fresh_profile=fresh_profile,
        )
        cdp_url = f"http://127.0.0.1:{port_number}"
        if account_id:
            self.remember_account_cdp(account_id, cdp_url)
        return {
            "account_id": account_id,
            "profile_key": profile_key,
            "profile_dir": str(profile_dir),
            "cdp_url": cdp_url,
            "pid": process.pid,
            "message": "chrome started",
        }

    def remember_account_cdp(self, account_id: str, cdp_url: str) -> None:
        account_id = str(account_id).strip()
        cdp_url = str(cdp_url).strip()
        if account_id and cdp_url:
            self._runtime_account_cdp[account_id] = cdp_url

    def resolve_cdp_url(
        self,
        account_id: str,
        *,
        cdp_port: int | None = None,
        cdp_url: str | None = None,
    ) -> str | None:
        if cdp_url and str(cdp_url).strip():
            return str(cdp_url).strip()
        if cdp_port is not None:
            return f"http://127.0.0.1:{int(cdp_port)}"
        remembered = self._runtime_account_cdp.get(account_id)
        if remembered:
            return remembered
        account_meta = self.config.account_sessions.get(account_id) or {}
        meta_url = str(account_meta.get("cdp_url") or "").strip()
        if meta_url:
            return meta_url
        return None

    def probe_account_session(
        self,
        account_id: str,
        *,
        cdp_port: int | None = None,
        cdp_url: str | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve_cdp_url(account_id, cdp_port=cdp_port, cdp_url=cdp_url)
        if not resolved:
            return {
                "account_id": account_id,
                "status": "unavailable",
                "message": "cdp_url not configured; start login browser first or pass cdp_port",
                "cdp_url": None,
            }
        self.remember_account_cdp(account_id, resolved)
        result = self._run_async(self._probe_executor.probe_session(resolved))
        result["account_id"] = account_id
        result["cdp_url"] = resolved
        return result

    def revalidate_account_session(
        self,
        account_id: str,
        *,
        cdp_port: int | None = None,
        cdp_url: str | None = None,
    ) -> dict[str, Any]:
        return self.probe_account_session(account_id, cdp_port=cdp_port, cdp_url=cdp_url)

    def _run_async(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=30)


class LocalBridgeServer:
    def __init__(self, *, bridge_config: LocalBridgeConfig, service: LocalBridgeService):
        self.bridge_config = bridge_config
        self.service = service
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        if not self.bridge_config.enabled:
            return
        handler_cls = _build_handler(self.service)
        self._server = ThreadingHTTPServer((self.bridge_config.host, self.bridge_config.port), handler_cls)
        self._thread = Thread(target=self._server.serve_forever, name="local-bridge", daemon=True)
        self._thread.start()
        logging.getLogger("local_agent").info(
            "local bridge listening on http://%s:%s",
            self.bridge_config.host,
            self.bridge_config.port,
        )

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


def _build_handler(service: LocalBridgeService):
    session_status_pattern = re.compile(r"^/bridge/accounts/([^/]+)/session-status$")
    revalidate_pattern = re.compile(r"^/bridge/accounts/([^/]+)/revalidate$")

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(204)
            self._set_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
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

            token = _extract_token(self.headers.get("Authorization"), parse_qs(parsed.query).get("token", [None])[0])
            if not service.require_token(token):
                self._write_json(401, {"detail": "invalid token"})
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
            token = _extract_token(self.headers.get("Authorization"), parse_qs(parsed.query).get("token", [None])[0])
            if not service.require_token(token):
                self._write_json(401, {"detail": "invalid token"})
                return

            body = self._read_json_body()
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

        def _set_cors_headers(self):
            origin = self.headers.get("Origin")
            allow_origin = origin if origin in {"http://127.0.0.1:5173", "http://localhost:5173"} else "*"
            self.send_header("Access-Control-Allow-Origin", allow_origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    return Handler


def _extract_token(auth_header: str | None, query_token: str | None) -> str | None:
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    if query_token:
        return query_token
    return None


def _extract_port(cdp_url: str) -> int | None:
    match = re.match(r"^https?://[^:]+:(\d+)", cdp_url.strip())
    if not match:
        return None
    return int(match.group(1))


def _query_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _NoopClient:
    async def report_login_progress(self, agent_id: str, session_id: str, status: str, *, error_message: str | None = None) -> None:
        return None

    async def complete_login_session(
        self,
        agent_id: str,
        session_id: str,
        *,
        platform_nickname: str | None = None,
        platform_home_url: str | None = None,
    ) -> None:
        return None

    async def fail_login_session(self, agent_id: str, session_id: str, error_message: str) -> None:
        return None
