#!/usr/bin/env python3
"""开发/演示环境全量重置：清空业务数据，保留代码与默认角色能力。

默认 dry-run，仅预览；使用 --apply --yes 真正执行。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from intelligence_engine.config import get_settings
from intelligence_engine.db import models  # noqa: F401
from intelligence_engine.db.models import (
    AccountSession,
    BehaviorProfile,
    BenchmarkGroup,
    BenchmarkGroupMember,
    BusinessAccountType,
    BusinessAccountTypeBenchmarkGroup,
    BusinessAccountTypeRuleSet,
    CandidateDecision,
    CommentSnapshot,
    ContentAssignment,
    ContentDiscoveryEvent,
    ContentIdentity,
    ContentOperatorNote,
    ContentSnapshot,
    ContentWorkflowState,
    CreatorMonitor,
    CreatorMonitorEvent,
    Employee,
    FetchLease,
    Job,
    JobEvent,
    KeywordRule,
    KeywordRuleSet,
    LocalAgent,
    NetworkEgressProfile,
    PlatformAccount,
    RiskPolicy,
    Role,
    TaskRun,
    TaskSchedule,
    TaskTemplate,
    User,
    UserRole,
)
from intelligence_engine.storage.repositories.product_repository import ProductRepository

# 子表优先删除；content_identity 需在清 latest_snapshot_id 后再删快照
CLEAR_TABLE_SPECS: list[tuple[str, type]] = [
    ("job_events", JobEvent),
    ("fetch_leases", FetchLease),
    ("jobs", Job),
    ("task_runs", TaskRun),
    ("creator_monitor_events", CreatorMonitorEvent),
    ("task_schedules", TaskSchedule),
    ("content_operator_notes", ContentOperatorNote),
    ("content_assignments", ContentAssignment),
    ("content_workflow_states", ContentWorkflowState),
    ("candidate_decisions", CandidateDecision),
    ("comment_snapshots", CommentSnapshot),
    ("content_discovery_events", ContentDiscoveryEvent),
    ("content_snapshots", ContentSnapshot),
    ("content_identity", ContentIdentity),
    ("creator_monitors", CreatorMonitor),
    ("benchmark_group_members", BenchmarkGroupMember),
    ("business_account_type_benchmark_groups", BusinessAccountTypeBenchmarkGroup),
    ("benchmark_groups", BenchmarkGroup),
    ("keyword_rules", KeywordRule),
    ("business_account_type_rule_sets", BusinessAccountTypeRuleSet),
    ("keyword_rule_sets", KeywordRuleSet),
    ("account_sessions", AccountSession),
    ("platform_accounts", PlatformAccount),
    ("local_agents", LocalAgent),
    ("task_templates", TaskTemplate),
    ("risk_policies", RiskPolicy),
    ("behavior_profiles", BehaviorProfile),
    ("network_egress_profiles", NetworkEgressProfile),
    ("business_account_types", BusinessAccountType),
    ("employees", Employee),
    ("user_roles", UserRole),
    ("users", User),
]

LOG_GLOB_PATTERNS = [
    "logs/*.log",
    "logs/**/*.log",
    "logs/*_latest.json",
    "logs/*.sql",
]
LOG_DIR_NAMES = ["logs/local_agent"]

# 仅项目内 profiles，绝不触碰系统 Chrome 用户数据目录
DEFAULT_PROFILES_ROOT = PROJECT_ROOT / "profiles"


@dataclass
class TablePlan:
    name: str
    model: type
    count: int


@dataclass
class PathPlan:
    path: Path
    kind: str  # file | dir


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _resolve_database_url(cli_url: str | None) -> str:
    if cli_url:
        return cli_url
    return get_settings().database_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _sqlite_path(url: str) -> Path | None:
    if not _is_sqlite(url):
        return None
    raw = url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _count_table(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _plan_tables(session: Session) -> list[TablePlan]:
    plans: list[TablePlan] = []
    for name, model in CLEAR_TABLE_SPECS:
        plans.append(TablePlan(name=name, model=model, count=_count_table(session, model)))
    plans.append(TablePlan(name="roles", model=Role, count=_count_table(session, Role)))
    return plans


def _plan_logs() -> list[PathPlan]:
    seen: set[Path] = set()
    items: list[PathPlan] = []
    for pattern in LOG_GLOB_PATTERNS:
        for path in sorted(PROJECT_ROOT.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                items.append(PathPlan(path=path, kind="file"))
    for rel in LOG_DIR_NAMES:
        directory = PROJECT_ROOT / rel
        if directory.is_dir() and directory not in seen:
            seen.add(directory)
            items.append(PathPlan(path=directory, kind="dir"))
    return items


def _plan_profiles(include_profiles: bool) -> list[PathPlan]:
    if not include_profiles:
        return []
    items: list[PathPlan] = []
    if DEFAULT_PROFILES_ROOT.is_dir():
        for child in sorted(DEFAULT_PROFILES_ROOT.iterdir()):
            if child.name.startswith("."):
                continue
            items.append(PathPlan(path=child, kind="dir"))
    return items


def _backup_sqlite(db_path: Path, backups_dir: Path) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"intelligence_engine_{_utc_stamp()}.db"
    shutil.copy2(db_path, target)
    return target


def _backup_postgres_hint(url: str) -> str:
    return (
        "PostgreSQL 备份请在本机执行 pg_dump，例如：\n"
        f'  pg_dump "{url}" -Fc -f backups/intelligence_engine_{_utc_stamp()}.dump'
    )


def _clear_business_data(session: Session, *, reseed_roles: bool) -> None:
    session.execute(update(ContentIdentity).values(latest_snapshot_id=None))
    session.flush()
    for _name, model in CLEAR_TABLE_SPECS:
        session.execute(delete(model))
    session.flush()
    if reseed_roles:
        session.execute(delete(Role))
        session.flush()
        ProductRepository(session).ensure_default_roles()
    else:
        ProductRepository(session).ensure_default_roles()


def _is_file_locked_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 32:
        return True
    message = str(exc).lower()
    return "being used by another process" in message or "另一个程序正在使用" in message


def _remove_paths(paths: list[PathPlan]) -> None:
    locked: list[Path] = []
    for item in paths:
        try:
            if item.kind == "dir" and item.path.is_dir():
                shutil.rmtree(item.path)
            elif item.path.is_file():
                item.path.unlink(missing_ok=True)
        except FileNotFoundError:
            continue
        except OSError as exc:
            if _is_file_locked_error(exc):
                locked.append(item.path)
            else:
                raise
    if locked:
        print()
        print("=" * 72)
        print("错误：无法删除以下日志/文件（被正在运行的服务占用）")
        print("=" * 72)
        for path in locked:
            try:
                rel = path.relative_to(PROJECT_ROOT)
            except ValueError:
                rel = path
            print(f"  - {rel}")
        print()
        print("请先停止本地服务，然后重新执行 reset：")
        print(r"  1. 在项目根目录双击 分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1")
        print(r"  2. 再双击 cd central_server; .\scripts\reset.ps1（会自动先 stop；若仍失败请手动 stop 后重试）")
        print(r"  3. 确认端口 8000 / 5173 已释放")
        print()
        raise SystemExit(3)


def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="重置开发/演示环境业务数据（默认 dry-run）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改（默认行为）")
    parser.add_argument("--apply", action="store_true", help="真正执行清空")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（必须与 --apply 同用）")
    parser.add_argument("--database-url", default=None, help="覆盖 INTEL_ENGINE_DATABASE_URL / .env")
    parser.add_argument("--backup-db", action="store_true", help="执行前备份数据库（SQLite 自动复制；PostgreSQL 打印 pg_dump 指引）")
    parser.add_argument(
        "--include-project-profiles",
        action="store_true",
        help="同时删除项目 profiles/ 下子目录（不含系统 Chrome 配置）",
    )
    parser.add_argument(
        "--reseed-roles",
        action="store_true",
        help="清空后删除并重建默认 roles；默认仅 ensure_default_roles 补缺",
    )
    args = parser.parse_args()

    apply = args.apply
    dry_run = not apply or args.dry_run
    if apply and args.dry_run:
        dry_run = False

    database_url = _resolve_database_url(args.database_url)
    connect_args = {"check_same_thread": False} if _is_sqlite(database_url) else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with SessionLocal() as session:
        table_plans = _plan_tables(session)
    log_plans = _plan_logs()
    profile_plans = _plan_profiles(args.include_project_profiles)

    _print_section("AMiracle 演示环境重置预览" if dry_run else "AMiracle 演示环境重置执行")
    print(f"数据库: {database_url}")
    print(f"模式: {'dry-run（未修改任何数据）' if dry_run else 'apply（将修改数据）'}")
    print(f"保留默认 roles: {'否（将删除并重建）' if args.reseed_roles else '是（清空用户后保留或补缺 admin/supervisor/operator/sales）'}")
    print(f"重置后 bootstrap: POST /api/product/bootstrap-default-roles（若 roles 已保留可跳过）")

    _print_section("将清空的数据库表（及当前记录数）")
    total_rows = 0
    for plan in table_plans:
        if plan.name == "roles":
            note = "（保留，仅 ensure 补缺）" if not args.reseed_roles else "（将删除并重建）"
            print(f"  {plan.name:40} {plan.count:8} 条{note}")
        else:
            print(f"  {plan.name:40} {plan.count:8} 条")
            total_rows += plan.count
    print(f"  {'— 业务表合计（不含 roles）':40} {total_rows:8} 条")

    _print_section("将删除的日志/报告文件")
    if not log_plans:
        print("  （无匹配文件）")
    for item in log_plans:
        print(f"  [{item.kind}] {item.path.relative_to(PROJECT_ROOT)}")

    _print_section("项目本地 Chrome Profiles")
    if not profile_plans:
        print("  （未启用；传 --include-project-profiles 才会删除）")
        print(f"  扫描根目录: {DEFAULT_PROFILES_ROOT}")
        if DEFAULT_PROFILES_ROOT.is_dir():
            for child in sorted(DEFAULT_PROFILES_ROOT.iterdir()):
                print(f"    - {child.name}/")
    else:
        print("  警告：仅删除下列项目目录，不会触碰系统 Chrome 用户数据。")
        for item in profile_plans:
            print(f"  [dir] {item.path}")

    _print_section("明确不会删除")
    print("  - 源代码、迁移、.venv")
    print("  - frontend/node_modules、构建缓存（未纳入本脚本）")
    print("  - 系统 Chrome 用户数据（%LOCALAPPDATA%\\Google\\Chrome\\User Data 等）")

    if dry_run:
        print()
        print("Dry-run 完成。真正执行请双击项目根目录：")
        print(r"  cd central_server; .\scripts\reset.ps1")
        print("（自动 stop → 输入 YES → 备份 → 清空业务数据 → 删除 profiles）")
        return 0

    if not args.yes:
        print()
        print("拒绝执行：必须同时传入 --apply 与 --yes")
        return 2

    if args.backup_db:
        if _is_sqlite(database_url):
            db_path = _sqlite_path(database_url)
            if db_path and db_path.is_file():
                backup_path = _backup_sqlite(db_path, PROJECT_ROOT / "backups")
                print(f"SQLite 已备份到: {backup_path}")
            else:
                print(f"警告：SQLite 文件不存在，跳过备份: {db_path}")
        else:
            print(_backup_postgres_hint(database_url))

    with SessionLocal() as session:
        _clear_business_data(session, reseed_roles=args.reseed_roles)
        session.commit()
        after = _plan_tables(session)

    _remove_paths(log_plans)
    _remove_paths(profile_plans)

    _print_section("重置完成 — 清空后记录数")
    for plan in after:
        print(f"  {plan.name:40} {plan.count:8} 条")

    print()
    print("下一步建议：")
    print("  1. central_server\scripts\start.ps1 启动前后端（见 docs/README.md）")
    print("  2. 浏览器打开前端，完成「初始化管理员」与组织管理")
    print("  3. 创建员工、账号、Agent，按 playbook 跑三类引擎")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
