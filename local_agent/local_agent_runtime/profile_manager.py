from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from local_agent_runtime.chrome_launcher import resolve_profile_dir

logger = logging.getLogger("local_agent")

FRESH_PROFILE_MARKER = "__fresh_profile__"


def stop_processes_on_port(port: int) -> None:
    """释放 remote-debugging-port，避免连到其它账号已打开的浏览器。"""
    if port < 1 or port > 65535:
        return
    if sys.platform == "win32":
        _stop_processes_on_port_windows(port)
    else:
        _stop_processes_on_port_unix(port)


def _stop_processes_on_port_windows(port: int) -> None:
    try:
        output = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        logger.warning("netstat failed for port %s: %s", port, exc)
        return
    needle = f":{port}"
    pids: set[int] = set()
    for line in output.splitlines():
        if needle not in line or "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    for pid in pids:
        if pid <= 4:
            continue
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        logger.info("stopped pid %s listening on port %s", pid, port)


def _stop_processes_on_port_unix(port: int) -> None:
    try:
        output = subprocess.check_output(["fuser", f"{port}/tcp"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return
    for token in output.split():
        if token.isdigit():
            subprocess.run(["kill", "-9", token], capture_output=True)


def clear_chromium_login_state(profile_dir: Path) -> None:
    """清除 Chromium/Edge Profile 中的登录 Cookie 与站点存储。"""
    targets = [
        profile_dir / "Default",
        profile_dir / "Profile 1",
    ]
    removable_names = [
        "Cookies",
        "Cookies-journal",
        "Local Storage",
        "Session Storage",
        "IndexedDB",
        "Network",
        "Service Worker",
        "Web Data",
        "Login Data",
    ]
    for base in targets:
        if not base.is_dir():
            continue
        for name in removable_names:
            path = base / name
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("failed clearing %s: %s", path, exc)


def prepare_profile_for_login(
    *,
    project_root: Path,
    profile_key: str,
    cdp_port: int,
    fresh_profile: bool = False,
) -> Path:
    # 不主动清理端口进程，避免影响同机其它运行中的流程；
    # 重新登录依赖中央重新分配 cdp_port + 当前账号 profile 数据清理来完成账号切换。
    profile_dir = resolve_profile_dir(project_root, profile_key)
    if fresh_profile:
        clear_chromium_login_state(profile_dir)
    return profile_dir
