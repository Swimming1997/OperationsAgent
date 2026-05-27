from __future__ import annotations

import socket

DEFAULT_BRIDGE_PORT = 18765
# 与前端 VITE 默认扫描范围一致（18765–18774，共 10 个）
DEFAULT_BRIDGE_PORT_ATTEMPTS = 10


def is_tcp_port_in_use(host: str, port: int) -> bool:
    """若 host:port 上已有服务在监听，返回 True。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def pick_available_bridge_port(
    host: str,
    preferred: int,
    *,
    max_attempts: int = DEFAULT_BRIDGE_PORT_ATTEMPTS,
) -> tuple[int, int | None]:
    """
    从 preferred 起向上尝试，返回 (选用端口, 被占用的原端口或 None)。
    若 preferred 可用则第二项为 None。
    """
    if preferred < 1024 or preferred > 65535:
        raise ValueError("bridge port must be between 1024 and 65535")
    attempts = max(1, min(max_attempts, 65535 - preferred + 1))
    for offset in range(attempts):
        port = preferred + offset
        if not is_tcp_port_in_use(host, port):
            return port, preferred if offset > 0 else None
    raise RuntimeError(
        f"no free bridge port on {host} in range {preferred}–{preferred + attempts - 1}; stop other local_agent processes"
    )
