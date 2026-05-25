$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

$PythonCode = @'
from __future__ import annotations

import fnmatch
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

root = Path(sys.argv[1]).resolve()

remove_dir_names = {"__pycache__", ".pytest_cache"}
for path in list(root.rglob("*")):
    if path.parts and ".venv" in path.parts:
        continue
    if path.is_dir() and path.name in remove_dir_names:
        shutil.rmtree(path, ignore_errors=True)
for pattern in ("*.pyc", "*.pyo"):
    for path in root.rglob(pattern):
        if ".venv" not in path.parts:
            path.unlink(missing_ok=True)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
zip_path = root / f"AMiracle-code-{stamp}.zip"

exclude_dirs = {
    ".venv",
    ".git",
    "node_modules",
    "dist",
    "data",
    "logs",
    "profiles",
    "packages",
    "backups",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}

exclude_file_patterns = {
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.bak",
    "*.zip",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.tsbuildinfo",
    ".coverage",
    ".DS_Store",
    "Thumbs.db",
}

for old_zip in root.glob("AMiracle-code-*.zip"):
    old_zip.unlink(missing_ok=True)

def rel_posix(path: Path) -> str:
    return path.relative_to(root).as_posix()

def excluded(path: Path) -> bool:
    rel = rel_posix(path)
    parts = set(rel.split("/"))
    if parts & exclude_dirs:
        return True
    if rel.startswith("central_server/frontend/node_modules/"):
        return True
    if rel.startswith("central_server/frontend/dist/"):
        return True
    if rel.startswith("local_agent/references/MediaCrawler/.git/"):
        return True
    if path.is_file():
        for pattern in exclude_file_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True
    return False

include_roots = [root / "central_server", root / "local_agent", root / "README.md", root / ".gitignore", root / "package_project.ps1", root / "package_project.bat"]

files: list[Path] = []
for include_root in include_roots:
    if not include_root.exists():
        continue
    if include_root.is_file():
        if not excluded(include_root):
            files.append(include_root)
        continue
    for path in include_root.rglob("*"):
        if path.is_file() and not excluded(path):
            files.append(path)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files, key=lambda item: rel_posix(item).lower()):
        archive.write(path, rel_posix(path))

forbidden_patterns = [
    ".venv/",
    ".git/",
    "node_modules/",
    "/dist/",
    "/data/",
    "/logs/",
    "/profiles/",
    "/packages/",
    "/backups/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
]
forbidden_suffixes = (".pyc", ".pyo", ".log", ".tmp", ".bak", ".zip", ".db", ".sqlite", ".sqlite3", ".tsbuildinfo")

with zipfile.ZipFile(zip_path, "r") as archive:
    names = archive.namelist()
    forbidden = [
        name for name in names
        if any(pattern in name for pattern in forbidden_patterns)
        or name.endswith(forbidden_suffixes)
        or name.endswith(".coverage")
        or name.endswith(".DS_Store")
        or name.endswith("Thumbs.db")
        or name.startswith("local_agent/references/MediaCrawler/.git/")
    ]

size_mb = zip_path.stat().st_size / (1024 * 1024)
print(f"Zip path: {zip_path}")
print(f"Zip size: {size_mb:.2f} MB")
print("First 100 files:")
for name in names[:100]:
    print(f"  {name}")
if forbidden:
    print("Forbidden runtime data found in zip: YES")
    for name in forbidden[:100]:
        print(f"  {name}")
else:
    print("Forbidden runtime data found in zip: NO")
'@

$TempScript = Join-Path $env:TEMP ("amiracle_package_" + [guid]::NewGuid().ToString("N") + ".py")
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($TempScript, $PythonCode, $Utf8NoBom)
try {
    & $PythonExe $TempScript $ProjectRoot
}
finally {
    if (Test-Path -LiteralPath $TempScript) {
        Remove-Item -LiteralPath $TempScript -Force -ErrorAction SilentlyContinue
    }
}
