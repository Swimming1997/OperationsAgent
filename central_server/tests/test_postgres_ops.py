from pathlib import Path

from scripts.postgres_ops import (
    build_backup_command,
    build_restore_command,
    build_verify_command,
)


def test_postgres_backup_command_uses_custom_portable_format(tmp_path):
    output = tmp_path / "backup.dump"
    command = build_backup_command("postgresql://user:pass@db/app", output)
    assert command[:4] == ["pg_dump", "--format=custom", "--no-owner", "--no-privileges"]
    assert f"--file={output}" in command


def test_postgres_restore_command_supports_clean_restore(tmp_path):
    source = tmp_path / "backup.dump"
    command = build_restore_command("postgresql://user:pass@db/app", source, clean=True)
    assert command[:3] == ["pg_restore", "--no-owner", "--no-privileges"]
    assert "--clean" in command
    assert "--if-exists" in command
    assert f"--dbname=postgresql://user:pass@db/app" in command


def test_postgres_verify_lists_archive(tmp_path):
    source = Path(tmp_path / "backup.dump")
    assert build_verify_command(source) == ["pg_restore", "--list", str(source)]

