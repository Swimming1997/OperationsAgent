from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from local_agent_runtime.storage.schema import initialize_schema


CDP_PORT_RANGE_START = 9300
CDP_PORT_RANGE_END = 9499
VALID_AUTH_STATUS = {
    "not_logged_in",
    "login_pending",
    "active",
    "error",
    "expired",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class LocalAccountRepository:
    """Local-first owner of platform accounts (xhs / douyin).

    The local SQLite database is the single source of truth for which
    accounts an employee manages on this machine, their login state and the
    Chrome profile / CDP port assigned to each account. Central only receives
    read-only monitoring snapshots later (see F5).
    """

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            initialize_schema(connection)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    # ---- queries -----------------------------------------------------------

    def list_accounts(self, *, platform: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as connection:
            if platform:
                rows = connection.execute(
                    "SELECT * FROM platform_account WHERE platform = ? ORDER BY created_at DESC",
                    (platform,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM platform_account ORDER BY created_at DESC"
                ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM platform_account WHERE id = ?",
                (account_id,),
            ).fetchone()
            return self._row_to_dict(row) if row else None

    # ---- mutations ---------------------------------------------------------

    def create_account(
        self,
        *,
        platform: str,
        display_name: str = "",
        account_role: str = "intelligence_collector",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        platform = str(platform).strip()
        if not platform:
            raise ValueError("platform is required")
        account_id = uuid.uuid4().hex
        profile_key = f"accounts/{account_id}"
        now = _now_iso()
        with self.connection() as connection:
            cdp_port = self._allocate_cdp_port(connection, account_id)
            connection.execute(
                """
                INSERT INTO platform_account(
                    id, platform, display_name, account_role, status, auth_status,
                    health_status, profile_key, cdp_port, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', 'not_logged_in', 'unknown', ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    platform,
                    str(display_name or "").strip(),
                    str(account_role or "intelligence_collector"),
                    profile_key,
                    cdp_port,
                    _json(metadata or {}),
                    now,
                    now,
                ),
            )
            connection.commit()
        account = self.get_account(account_id)
        assert account is not None
        return account

    def update_account(
        self,
        account_id: str,
        *,
        display_name: str | None = None,
        status: str | None = None,
        account_role: str | None = None,
    ) -> dict[str, Any]:
        sets: list[str] = []
        params: list[Any] = []
        if display_name is not None:
            sets.append("display_name = ?")
            params.append(str(display_name).strip())
        if status is not None:
            sets.append("status = ?")
            params.append(str(status).strip())
        if account_role is not None:
            sets.append("account_role = ?")
            params.append(str(account_role).strip())
        if not sets:
            account = self.get_account(account_id)
            if account is None:
                raise ValueError("account not found")
            return account
        sets.append("updated_at = ?")
        params.append(_now_iso())
        params.append(account_id)
        with self.connection() as connection:
            cursor = connection.execute(
                f"UPDATE platform_account SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            connection.commit()
            if cursor.rowcount == 0:
                raise ValueError("account not found")
        account = self.get_account(account_id)
        assert account is not None
        return account

    def delete_account(self, account_id: str) -> bool:
        with self.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM platform_account WHERE id = ?",
                (account_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

    def allocate_cdp_port(self, account_id: str) -> int:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT cdp_port FROM platform_account WHERE id = ?",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ValueError("account not found")
            if row["cdp_port"]:
                return int(row["cdp_port"])
            port = self._allocate_cdp_port(connection, account_id)
            connection.execute(
                "UPDATE platform_account SET cdp_port = ?, updated_at = ? WHERE id = ?",
                (port, _now_iso(), account_id),
            )
            connection.commit()
            return port

    def mark_login_pending(self, account_id: str) -> dict[str, Any]:
        return self._set_status(account_id, auth_status="login_pending")

    def mark_logged_in(
        self,
        account_id: str,
        *,
        platform_nickname: str | None = None,
        platform_home_url: str | None = None,
        external_account_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE platform_account SET
                    auth_status = 'active',
                    health_status = 'healthy',
                    platform_nickname = COALESCE(?, platform_nickname),
                    platform_home_url = COALESCE(?, platform_home_url),
                    external_account_id = COALESCE(?, external_account_id),
                    last_verified_at = ?,
                    last_success_at = ?,
                    consecutive_failures = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    platform_nickname,
                    platform_home_url,
                    external_account_id,
                    now,
                    now,
                    now,
                    account_id,
                ),
            )
            connection.commit()
            if cursor.rowcount == 0:
                raise ValueError("account not found")
        account = self.get_account(account_id)
        assert account is not None
        return account

    def mark_login_failed(self, account_id: str, *, error: str | None = None) -> dict[str, Any]:
        now = _now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE platform_account SET
                    auth_status = 'error',
                    health_status = 'unhealthy',
                    last_failure_at = ?,
                    consecutive_failures = consecutive_failures + 1,
                    metadata_json = json_set(
                        CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END,
                        '$.last_login_error', ?
                    ),
                    updated_at = ?
                WHERE id = ?
                """,
                (now, str(error or ""), now, account_id),
            )
            connection.commit()
            if cursor.rowcount == 0:
                raise ValueError("account not found")
        account = self.get_account(account_id)
        assert account is not None
        return account

    def set_auth_status(self, account_id: str, auth_status: str) -> dict[str, Any]:
        return self._set_status(account_id, auth_status=auth_status)

    # ---- internals ---------------------------------------------------------

    def _set_status(self, account_id: str, *, auth_status: str) -> dict[str, Any]:
        if auth_status not in VALID_AUTH_STATUS:
            raise ValueError(f"invalid auth_status: {auth_status}")
        with self.connection() as connection:
            cursor = connection.execute(
                "UPDATE platform_account SET auth_status = ?, updated_at = ? WHERE id = ?",
                (auth_status, _now_iso(), account_id),
            )
            connection.commit()
            if cursor.rowcount == 0:
                raise ValueError("account not found")
        account = self.get_account(account_id)
        assert account is not None
        return account

    def _allocate_cdp_port(self, connection: sqlite3.Connection, account_id: str) -> int:
        used = {
            int(row["cdp_port"])
            for row in connection.execute(
                "SELECT cdp_port FROM platform_account WHERE cdp_port IS NOT NULL"
            ).fetchall()
        }
        span = CDP_PORT_RANGE_END - CDP_PORT_RANGE_START + 1
        seed = int(uuid.UUID(account_id).int % span) if _is_hex_uuid(account_id) else 0
        for offset in range(span):
            candidate = CDP_PORT_RANGE_START + ((seed + offset) % span)
            if candidate not in used:
                return candidate
        raise RuntimeError("no free CDP port available in local range")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        metadata = data.get("metadata_json")
        try:
            data["metadata"] = json.loads(metadata) if metadata else {}
        except (TypeError, ValueError):
            data["metadata"] = {}
        data.pop("metadata_json", None)
        return data


def _is_hex_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
