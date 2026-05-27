import argparse
import asyncio
import logging
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from local_agent_runtime.bridge_port import pick_available_bridge_port
from local_agent_runtime.config import load_agent_runtime_config
from local_agent_runtime.local_bridge import LocalBridgeConfig, LocalBridgeServer, LocalBridgeService
from local_agent_runtime.runtime import AgentRuntimeConfig, CenterClient, LocalAgentRuntime, build_agent_capabilities_payload
from local_agent_runtime.runtime_pid import clear_runtime_pid, write_runtime_pid


def parse_args():
    parser = argparse.ArgumentParser(description="Run AMiracle Local Agent Runtime V1.")
    parser.add_argument("--config", default="configs/local_agent.employee.example.toml", help="Local agent TOML/JSON config path.")
    parser.add_argument("--center-url", default=None)
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--cdp-url", default=None)
    parser.add_argument("--once", action="store_true", help="Claim and execute once, then exit.")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--project-root", default=None, help="Local Agent root for profiles/accounts/{profile_key}.")
    parser.add_argument("--bridge-port", type=int, default=None, help="Local bridge port (default from config).")
    parser.add_argument("--bridge-token", default=None, help="Local bridge bearer token override.")
    parser.add_argument("--disable-bridge", action="store_true", help="Disable local bridge API.")
    return parser.parse_args()


def configure_logging(log_dir: str) -> None:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / "local_agent.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [Local Agent] %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def print_startup_banner(config: AgentRuntimeConfig, *, config_path: str) -> None:
    project_root = Path(config.project_root or Path.cwd()).resolve()
    profiles_root = project_root / "profiles" / "accounts"
    caps = build_agent_capabilities_payload(config)
    print(f"[Local Agent] Config file: {config_path}")
    print(f"[Local Agent] Connecting to {config.center_base_url}")
    print(f"[Local Agent] device_name={config.device_name}")
    print(f"[Local Agent] machine_fingerprint={config.machine_fingerprint}")
    if config.employee_id:
        print(f"[Local Agent] employee_id={config.employee_id} (from config; prefer Admin /agents UI binding)")
    else:
        print("[Local Agent] employee binding: assign in Admin /agents after this device registers")
    print(f"[Local Agent] project_root={project_root}")
    print(f"[Local Agent] profiles_root={profiles_root}")
    print(f"[Local Agent] heartbeat_interval_seconds={config.heartbeat_interval_seconds}")
    if config.local_bridge_enabled:
        print(f"[Local Agent] local_bridge=http://{config.local_bridge_host}:{config.local_bridge_port}")
    else:
        print("[Local Agent] local_bridge=disabled")
    print(f"[Local Agent] supports_account_login={caps.get('supports_account_login')}")
    print(f"[Local Agent] job_types={caps.get('job_types')}")


def resolve_bridge_port(config: AgentRuntimeConfig, logger: logging.Logger) -> AgentRuntimeConfig:
    if not config.local_bridge_enabled:
        return config
    port, replaced_from = pick_available_bridge_port(config.local_bridge_host, config.local_bridge_port)
    if replaced_from is not None:
        msg = f"bridge port {replaced_from} in use, using {port}"
        print(f"[Local Agent] {msg}")
        logger.info(msg)
    return replace(config, local_bridge_port=port)


def with_cli_overrides(config: AgentRuntimeConfig, args) -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        center_base_url=args.center_url or config.center_base_url,
        agent_id=args.agent_id or config.agent_id,
        employee_id=config.employee_id,
        device_name=config.device_name,
        machine_fingerprint=config.machine_fingerprint,
        agent_version=config.agent_version,
        cdp_url=args.cdp_url or config.cdp_url,
        poll_interval_seconds=config.poll_interval_seconds,
        heartbeat_interval_seconds=config.heartbeat_interval_seconds,
        max_jobs_per_claim=config.max_jobs_per_claim,
        local_bridge_enabled=(False if args.disable_bridge else config.local_bridge_enabled),
        local_bridge_host=config.local_bridge_host,
        local_bridge_port=args.bridge_port or config.local_bridge_port,
        local_bridge_token=args.bridge_token if args.bridge_token is not None else config.local_bridge_token,
        supported_job_types=config.supported_job_types,
        account_sessions=config.account_sessions,
        project_root=args.project_root or config.project_root or str(Path(__file__).resolve().parents[1]),
    )


async def main() -> None:
    args = parse_args()
    configure_logging(args.log_dir)
    logger = logging.getLogger("local_agent")
    config = resolve_bridge_port(with_cli_overrides(load_agent_runtime_config(args.config), args), logger)
    project_root = Path(config.project_root or Path(__file__).resolve().parents[1])
    pid_path = write_runtime_pid(project_root)
    print(f"[Local Agent] PID {pid_path.read_text(encoding='ascii').strip()} -> {pid_path}")
    print_startup_banner(config, config_path=args.config)
    client = CenterClient(base_url=config.center_base_url)
    runtime = LocalAgentRuntime(config=config, client=client)
    bridge_server: LocalBridgeServer | None = None
    agent_id: str | None = None
    try:
        try:
            await client.check_health()
        except Exception as exc:
            health_url = f"{config.center_base_url.rstrip('/')}/api/health"
            logger.error("central not reachable: %s", exc)
            print("")
            print("[Local Agent] ERROR: Cannot reach Central API.")
            print(f"  URL tried: {health_url}")
            print("  1) Start Central first and wait for /api/health to return ok.")
            print("  2) Wait until you see: Backend ready (.../api/health)")
            print("  3) If Central was just restarted, wait 5-10s and start Local Agent again.")
            print("  4) Check Central FastAPI logs for startup errors.")
            print(f"  Detail: {exc}")
            print("")
            raise SystemExit(1) from exc
        agent_id = await runtime.ensure_registered()
        config = runtime.config
        print(f"[Local Agent] Registered as {config.device_name} (agent_id={agent_id})")
        if config.local_bridge_enabled:
            bridge_server = LocalBridgeServer(
                bridge_config=LocalBridgeConfig(
                    enabled=config.local_bridge_enabled,
                    host=config.local_bridge_host,
                    port=config.local_bridge_port,
                    token=config.local_bridge_token,
                ),
                service=LocalBridgeService(config=config, loop=asyncio.get_running_loop()),
            )
            bridge_server.start()
        logger.info(
            "registered agent_id=%s device_name=%s employee_id=%s",
            agent_id,
            config.device_name,
            config.employee_id,
        )
        if args.once:
            handled = await runtime.run_once()
            logger.info("local agent runtime once complete handled_jobs=%s agent_id=%s", handled, runtime.agent_id)
        else:
            await runtime.run_forever()
    finally:
        if bridge_server:
            bridge_server.stop()
        if agent_id:
            try:
                await runtime.mark_offline(agent_id)
                logger.info("marked agent offline agent_id=%s", agent_id)
            except Exception as exc:
                logger.warning("failed to mark agent offline: %s", exc)
        await client.aclose()
        clear_runtime_pid(project_root)


if __name__ == "__main__":
    asyncio.run(main())
