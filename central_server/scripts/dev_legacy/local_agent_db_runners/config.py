# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from intelligence_engine.local_agent.runtime import AgentRuntimeConfig


def load_agent_runtime_config(path: str | Path) -> AgentRuntimeConfig:
    config_path = Path(path)
    data = _load_mapping(config_path)
    accounts = data.get("accounts") or {}
    account_sessions: dict[str, dict[str, Any]] = {}
    for account_id, account_config in accounts.items():
        if not isinstance(account_config, dict):
            continue
        session_mode = account_config.get("session_mode") or "cdp"
        if session_mode == "cdp":
            account_sessions[str(account_id)] = {
                "cdp_url": account_config.get("cdp_url"),
                "profile_ref": account_config.get("profile_ref"),
                "session_mode": session_mode,
            }
        else:
            account_sessions[str(account_id)] = dict(account_config)
    return AgentRuntimeConfig(
        center_base_url=data.get("center_url", "http://127.0.0.1:8000"),
        agent_id=data.get("agent_id"),
        employee_id=data.get("employee_id"),
        device_name=data.get("device_name") or AgentRuntimeConfig().device_name,
        machine_fingerprint=data.get("machine_fingerprint") or AgentRuntimeConfig().machine_fingerprint,
        agent_version=data.get("agent_version", "0.1.0"),
        cdp_url=data.get("cdp_url"),
        poll_interval_seconds=float(data.get("claim_interval_seconds", data.get("poll_interval_seconds", 5))),
        heartbeat_interval_seconds=float(data.get("heartbeat_interval_seconds", 30)),
        max_jobs_per_claim=int(data.get("max_concurrent_jobs", data.get("max_jobs_per_claim", 1))),
        supported_job_types=tuple(data.get("supported_job_types") or AgentRuntimeConfig().supported_job_types),
        account_sessions=account_sessions,
        project_root=_resolve_project_root(data.get("project_root"), config_path),
    )


def _resolve_project_root(value: str | None, config_path: Path) -> str | None:
    if not value:
        return None
    if value in {".", "./"}:
        return str(config_path.resolve().parents[1])
    return str(value)


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"local agent config not found: {path}")
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() in {".toml", ".tml"}:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"unsupported local agent config format: {path.suffix}")
