from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def build_backup_command(database_url: str, output_path: Path) -> list[str]:
    return [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={output_path}",
        database_url,
    ]


def build_restore_command(database_url: str, input_path: Path, *, clean: bool) -> list[str]:
    command = ["pg_restore", "--no-owner", "--no-privileges"]
    if clean:
        command.extend(["--clean", "--if-exists"])
    command.extend([f"--dbname={database_url}", str(input_path)])
    return command


def build_verify_command(input_path: Path) -> list[str]:
    return ["pg_restore", "--list", str(input_path)]


def require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name} is not available on PATH")


def default_backup_path(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return root / "backups" / f"intelligence_engine_{stamp}.dump"


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PostgreSQL backup, verification, and restore helper.")
    parser.add_argument("action", choices=["backup", "verify", "restore"])
    parser.add_argument("--database-url", default=os.getenv("INTEL_ENGINE_DATABASE_URL"))
    parser.add_argument("--file")
    parser.add_argument("--clean", action="store_true", help="Drop existing objects before restore.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.action == "backup":
        if not args.database_url:
            raise SystemExit("backup requires --database-url or INTEL_ENGINE_DATABASE_URL")
        require_executable("pg_dump")
        output = Path(args.file) if args.file else default_backup_path(root)
        output.parent.mkdir(parents=True, exist_ok=True)
        run_command(build_backup_command(args.database_url, output))
        require_executable("pg_restore")
        run_command(build_verify_command(output))
        print(output.resolve())
        return 0

    if not args.file:
        raise SystemExit(f"{args.action} requires --file")
    input_path = Path(args.file)
    if not input_path.is_file():
        raise SystemExit(f"backup file not found: {input_path}")
    require_executable("pg_restore")
    if args.action == "verify":
        run_command(build_verify_command(input_path))
        print(input_path.resolve())
        return 0
    if not args.database_url:
        raise SystemExit("restore requires --database-url or INTEL_ENGINE_DATABASE_URL")
    run_command(build_restore_command(args.database_url, input_path, clean=args.clean))
    print(input_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

