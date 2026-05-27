import type { LocalBridgeDiscoveredAgent, LocalBridgeSessionStatus, LocalBridgeStartResult } from '../types/api';

const DEFAULT_BRIDGE_HOST = '127.0.0.1';
const DEFAULT_BRIDGE_PORTS = [18765, 18766, 18767, 18768, 18769, 18770, 18771, 18772, 18773, 18774];

function bridgeHost(): string {
  const base = (import.meta.env.VITE_LOCAL_BRIDGE_URL as string | undefined)?.trim();
  if (!base) return DEFAULT_BRIDGE_HOST;
  try {
    return new URL(base).hostname || DEFAULT_BRIDGE_HOST;
  } catch {
    return DEFAULT_BRIDGE_HOST;
  }
}

/** 扫描端口列表：环境变量 VITE_LOCAL_BRIDGE_PORTS=18765,18766 或默认 18765–18774 */
export function getLocalBridgeScanPorts(): number[] {
  const raw = (import.meta.env.VITE_LOCAL_BRIDGE_PORTS as string | undefined)?.trim();
  if (raw) {
    const ports = raw.split(/[,;\s]+/).map((part) => parseInt(part, 10)).filter((n) => n >= 1024 && n <= 65535);
    if (ports.length) return [...new Set(ports)];
  }
  const single = (import.meta.env.VITE_LOCAL_BRIDGE_URL as string | undefined)?.trim();
  if (single) {
    try {
      const port = new URL(single).port;
      if (port) return [parseInt(port, 10)];
    } catch {
      /* use default range */
    }
  }
  return [...DEFAULT_BRIDGE_PORTS];
}

function bridgeBaseUrl(port: number): string {
  return `http://${bridgeHost()}:${port}`;
}

async function bridgeRequestAt<T>(port: number, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${bridgeBaseUrl(port)}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload?.detail === 'string' ? payload.detail : '本机助手请求失败';
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

async function bridgeRequestOnPorts<T>(
  path: string,
  init: RequestInit | undefined,
  ports: number[],
): Promise<{ data: T; port: number }> {
  const ordered = [...new Set(ports.filter((port) => port >= 1024 && port <= 65535))];
  if (!ordered.length) {
    throw new Error('本机 bridge 无可用端口，请先启动 local_agent');
  }
  let lastError: Error | null = null;
  for (const port of ordered) {
    try {
      const data = await bridgeRequestAt<T>(port, path, init);
      return { data, port };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
    }
  }
  throw lastError ?? new Error('本机 bridge 请求失败');
}

export async function localBridgeHealthcheck(): Promise<{ status: string; ports: number[] }> {
  const ports = getLocalBridgeScanPorts();
  const results = await Promise.all(
    ports.map(async (port) => {
      try {
        const body = await bridgeRequestAt<{ status: string }>(port, '/healthz');
        return body.status === 'ok' ? port : null;
      } catch {
        return null;
      }
    }),
  );
  const alive = results.filter((port): port is number => port !== null);
  return { status: alive.length ? 'ok' : 'unavailable', ports: alive };
}

export function startLocalBridgeChrome(
  payload: {
    account_id: string;
    profile_key?: string | null;
    port?: number | null;
    url?: string;
  },
  options?: { ports?: number[] },
) {
  const ports = options?.ports?.length ? options.ports : getLocalBridgeScanPorts();
  return bridgeRequestOnPorts<LocalBridgeStartResult>('/bridge/chrome/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, ports).then((result) => result.data);
}

export function fetchLocalBridgeSessionStatus(
  accountId: string,
  options?: { ports?: number[]; cdp_port?: number | null },
) {
  const ports = options?.ports?.length ? options.ports : getLocalBridgeScanPorts();
  const query = options?.cdp_port ? `?cdp_port=${options.cdp_port}` : '';
  return bridgeRequestOnPorts<LocalBridgeSessionStatus>(
    `/bridge/accounts/${accountId}/session-status${query}`,
    undefined,
    ports,
  ).then((result) => result.data);
}

export function revalidateLocalBridgeSession(
  accountId: string,
  options?: { ports?: number[]; cdp_port?: number | null },
) {
  const ports = options?.ports?.length ? options.ports : getLocalBridgeScanPorts();
  return bridgeRequestOnPorts<LocalBridgeSessionStatus>(
    `/bridge/accounts/${accountId}/revalidate`,
    {
      method: 'POST',
      body: JSON.stringify(options?.cdp_port ? { cdp_port: options.cdp_port } : {}),
    },
    ports,
  ).then((result) => result.data);
}

function dedupeDiscovered(items: LocalBridgeDiscoveredAgent[]): LocalBridgeDiscoveredAgent[] {
  const seen = new Set<string>();
  const out: LocalBridgeDiscoveredAgent[] = [];
  for (const item of items) {
    const key = item.agent_id || `${item.device_name}:${item.machine_fingerprint}:${item.bridge_port}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

/** 扫描本机多个 bridge 端口，汇总 discover 结果 */
export async function discoverLocalBridgeAgents(): Promise<{ items: LocalBridgeDiscoveredAgent[]; alive_ports: number[] }> {
  const ports = getLocalBridgeScanPorts();
  const alive_ports: number[] = [];
  const collected: LocalBridgeDiscoveredAgent[] = [];

  await Promise.all(
    ports.map(async (port) => {
      try {
        await bridgeRequestAt<{ status: string }>(port, '/healthz');
        alive_ports.push(port);
        const body = await bridgeRequestAt<{ items: Array<Omit<LocalBridgeDiscoveredAgent, 'bridge_port' | 'bridge_url'>> }>(
          port,
          '/bridge/agents/discover',
        );
        for (const item of body.items || []) {
          collected.push({
            ...item,
            bridge_port: port,
            bridge_url: item.bridge_url || bridgeBaseUrl(port),
          });
        }
      } catch {
        /* port not listening */
      }
    }),
  );

  alive_ports.sort((a, b) => a - b);
  return { items: dedupeDiscovered(collected), alive_ports };
}
