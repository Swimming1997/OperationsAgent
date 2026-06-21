from __future__ import annotations

import asyncio
import hmac
import logging
import re
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from local_agent_runtime.account_login_executor import AccountLoginExecutor
from local_agent_runtime.chrome_launcher import launch_managed_chrome
from local_agent_runtime.local_bridge_http import build_local_bridge_handler, is_trusted_origin
from local_agent_runtime.local_workspace import LocalWorkspaceServiceMixin
from local_agent_runtime.runtime import AgentRuntimeConfig
from local_agent_runtime.storage.repository import LocalIntelligenceRepository


@dataclass(frozen=True)
class LocalBridgeConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 18765
    token: str | None = None


class LocalBridgeService(LocalWorkspaceServiceMixin):
    def __init__(
        self,
        *,
        config: AgentRuntimeConfig,
        loop: asyncio.AbstractEventLoop,
        repository: LocalIntelligenceRepository | None = None,
        collection_service: Any | None = None,
        action_service: Any | None = None,
        account_service: Any | None = None,
    ):
        self.config = config
        self.loop = loop
        self.project_root = Path(config.project_root or Path.cwd()).resolve()
        self.repository = repository
        self.web_root = Path(__file__).resolve().parent / "web"
        self._probe_executor = AccountLoginExecutor(project_root=self.project_root, client=_NoopClient())
        if collection_service is not None:
            self.local_collection = collection_service
        elif repository is not None:
            from local_agent_runtime.local_tasks import LocalCollectionService

            self.local_collection = LocalCollectionService(
                config=config,
                repository=repository,
                account_session_resolver=self._resolve_account_session_meta,
            )
        else:
            self.local_collection = None
        if action_service is not None:
            self.local_actions = action_service
        elif repository is not None:
            from local_agent_runtime.local_actions import LocalContentActionService

            self.local_actions = LocalContentActionService(
                config=config,
                repository=repository,
                account_sessions_provider=self._list_collection_account_sessions,
            )
        else:
            self.local_actions = None
        # account_id -> cdp_url，由本进程 chrome/start 或前端传入端口写入
        self._runtime_account_cdp: dict[str, str] = {}
        if account_service is not None:
            self.local_accounts = account_service
        else:
            from local_agent_runtime.local_accounts import LocalAccountService
            from local_agent_runtime.storage.account_repository import LocalAccountRepository

            account_repository = LocalAccountRepository(self._resolve_local_database_path())
            self.local_accounts = LocalAccountService(
                project_root=self.project_root,
                repository=account_repository,
                loop=self.loop,
                on_cdp_resolved=self.remember_account_cdp,
            )

    def _resolve_local_database_path(self) -> Path:
        if self.repository is not None:
            return Path(self.repository.database_path)
        configured = getattr(self.config, "local_database_path", None)
        database_path = Path(configured) if configured else self.project_root / "data" / "local_intelligence.db"
        if not database_path.is_absolute():
            database_path = self.project_root / database_path
        return database_path

    # ---- platform account management (local-first) -------------------------

    def list_accounts(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        return self.local_accounts.list_accounts(query)

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        return self.local_accounts.get_account(account_id)

    def create_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.local_accounts.create_account(payload)

    def update_account_record(self, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.local_accounts.update_account(account_id, payload)

    def delete_account(self, account_id: str) -> dict[str, Any]:
        return self.local_accounts.delete_account(account_id)

    def start_account_login(self, account_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.local_accounts.start_login(account_id, payload or {})

    def require_token(self, token: str | None) -> bool:
        expected = self.config.local_bridge_token
        if not expected:
            return True
        return bool(token and hmac.compare_digest(token, expected))

    def authorize_request(
        self,
        *,
        token: str | None,
        origin: str | None,
        host: str | None,
        fetch_site: str | None,
    ) -> bool:
        if self.config.local_bridge_token:
            return self.require_token(token)
        if fetch_site and fetch_site.lower() == "cross-site":
            return False
        return is_trusted_origin(origin, host)

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

    def _list_collection_account_sessions(self) -> list[dict[str, Any]]:
        """Logged-in local accounts usable for parallel collection (local-first).

        Each entry is {account_id, cdp_url, label}. Only XHS accounts whose login
        browser CDP can be resolved are returned, so the detail dispatcher can run
        one worker per account in parallel.
        """
        accounts = getattr(self, "local_accounts", None)
        if accounts is None:
            return []
        try:
            records = accounts.list_accounts({"platform": ["xhs"]}).get("items", [])
        except Exception:  # pragma: no cover - defensive
            return []
        sessions: list[dict[str, Any]] = []
        for record in records:
            if str(record.get("auth_status") or "") != "active":
                continue
            account_id = str(record.get("id") or "").strip()
            if not account_id:
                continue
            cdp_port = record.get("cdp_port")
            resolved = self.resolve_cdp_url(
                account_id,
                cdp_port=int(cdp_port) if cdp_port else None,
            )
            if not resolved:
                continue
            sessions.append(
                {
                    "account_id": account_id,
                    "cdp_url": resolved,
                    "label": record.get("platform_nickname") or record.get("display_name"),
                }
            )
        return sessions

    def _resolve_account_session_meta(self, account_id: str) -> dict[str, Any] | None:
        """Resolve a local account id to a collection session_meta (local-first).

        Looks up the account's own managed Chrome CDP endpoint (the one started
        during local login), so collection runs against the account's profile
        without any central ready-session handshake.
        """
        account_id = str(account_id or "").strip()
        if not account_id:
            return None
        cdp_port: int | None = None
        account = getattr(self, "local_accounts", None)
        if account is not None:
            try:
                record = account.get_account(account_id)
            except Exception:  # pragma: no cover - defensive
                record = None
            if record and record.get("cdp_port"):
                cdp_port = int(record["cdp_port"])
        resolved = self.resolve_cdp_url(account_id, cdp_port=cdp_port)
        return {"cdp_url": resolved} if resolved else None

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

    def _run_async(self, coro, *, timeout: float = 65):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

class LocalBridgeServer:
    def __init__(self, *, bridge_config: LocalBridgeConfig, service: LocalBridgeService):
        if bridge_config.token != service.config.local_bridge_token:
            raise ValueError("Local Bridge token must match AgentRuntimeConfig.local_bridge_token")
        self.bridge_config = bridge_config
        self.service = service
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        if not self.bridge_config.enabled:
            return
        handler_cls = build_local_bridge_handler(self.service)
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


def _extract_port(cdp_url: str) -> int | None:
    match = re.match(r"^https?://[^:]+:(\d+)", cdp_url.strip())
    if not match:
        return None
    return int(match.group(1))


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
