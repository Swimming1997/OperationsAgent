#!/usr/bin/env python3
"""为单个平台账号启动独立 Chrome（CDP），便于员工电脑多账号并行登录。"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_ROOT = PROJECT_ROOT / "profiles" / "accounts"


def _find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_PATH"),
        os.environ.get("BROWSER_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    found = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("msedge")
    if found:
        return found
    raise FileNotFoundError("未找到 Chrome/Edge，请安装浏览器或设置 CHROME_PATH/BROWSER_PATH")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动带远程调试端口的 Chrome 实例（项目 profiles 目录）")
    parser.add_argument("--account-key", required=True, help="账号标识，用于 profile 子目录名，如 acc001")
    parser.add_argument(
        "--profile-dir",
        default=None,
        help="完整 profile 路径；默认 profiles/accounts/<account-key>",
    )
    parser.add_argument("--port", type=int, default=9222, help="remote-debugging-port，多账号请递增，如 9223")
    parser.add_argument(
        "--url",
        default="https://www.xiaohongshu.com/explore",
        help="启动后打开的 URL",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不启动")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile_dir = Path(args.profile_dir) if args.profile_dir else DEFAULT_PROFILES_ROOT / args.account_key
    profile_dir = profile_dir.resolve()
    if not str(profile_dir).startswith(str(DEFAULT_PROFILES_ROOT.resolve())):
        print(f"拒绝：profile 必须在项目目录内: {DEFAULT_PROFILES_ROOT}", file=sys.stderr)
        return 2

    profile_dir.mkdir(parents=True, exist_ok=True)
    chrome = _find_chrome()
    cmd = [
        chrome,
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={args.port}",
        "--no-first-run",
        "--no-default-browser-check",
        args.url,
    ]
    print("Chrome profile:", profile_dir)
    print("CDP URL:", f"http://127.0.0.1:{args.port}")
    print("命令:", " ".join(f'"{part}"' if " " in part else part for part in cmd))
    if args.dry_run:
        return 0
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_path = PROJECT_ROOT / "logs" / "runtime" / "chrome-cdp.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(process.pid), encoding="ascii")
    print("已启动（后台进程）。请在浏览器中完成小红书登录。")
    print("PID file:", pid_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
