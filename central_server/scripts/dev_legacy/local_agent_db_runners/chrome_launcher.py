# legacy DB-coupled smoke tool; not part of the formal Local Agent Runtime.
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_chrome_executable() -> str:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    found = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    raise FileNotFoundError("Chrome executable not found")


def resolve_profile_dir(project_root: Path, profile_key: str) -> Path:
    profiles_root = (project_root / "profiles").resolve()
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
) -> tuple[Path, subprocess.Popen[bytes]]:
    profile_dir = resolve_profile_dir(project_root, profile_key)
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
    return profile_dir, process
