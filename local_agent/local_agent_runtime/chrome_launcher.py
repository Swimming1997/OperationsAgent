from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_chrome_executable() -> str:
    candidates = [
        os.environ.get("CHROME_PATH"),
        os.environ.get("BROWSER_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    found = (
        shutil.which("chrome")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("msedge")
    )
    if found:
        return found
    raise FileNotFoundError(
        "Chrome executable not found. Install Chrome/Edge, or set CHROME_PATH/BROWSER_PATH."
    )


def resolve_profile_dir(project_root: Path, profile_key: str) -> Path:
    profiles_root = (project_root / "profiles" / "accounts").resolve()
    profile_dir = (profiles_root / profile_key).resolve()
    if not str(profile_dir).startswith(str(profiles_root)):
        raise ValueError(f"profile_key escapes profiles root: {profile_key}")
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def launch_managed_chrome(
    *,
    project_root: Path,
    profile_key: str,
    cdp_port: int,
    url: str = "https://www.xiaohongshu.com/explore",
    fresh_profile: bool = False,
) -> tuple[Path, subprocess.Popen[bytes]]:
    from local_agent_runtime.profile_manager import prepare_profile_for_login

    profile_dir = prepare_profile_for_login(
        project_root=project_root,
        profile_key=profile_key,
        cdp_port=cdp_port,
        fresh_profile=fresh_profile,
    )
    chrome = find_chrome_executable()
    cmd = [
        chrome,
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    try:
        from local_agent_runtime.runtime_pid import write_chrome_pid

        write_chrome_pid(project_root, process.pid)
    except Exception:
        pass
    return profile_dir, process
