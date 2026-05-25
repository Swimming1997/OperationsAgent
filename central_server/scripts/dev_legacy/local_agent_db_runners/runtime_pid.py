# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

import os
from pathlib import Path


def runtime_pid_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / "logs" / "runtime" / "local-agent.pid"


def write_runtime_pid(project_root: str | Path) -> Path:
    path = runtime_pid_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="ascii")
    return path


def clear_runtime_pid(project_root: str | Path) -> None:
    path = runtime_pid_path(project_root)
    if path.exists():
        path.unlink(missing_ok=True)
