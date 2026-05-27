export function listDeclaredJobTypes(capabilities?: Record<string, unknown> | null): string[] {
  if (!capabilities) return [];
  const declared: string[] = [];
  for (const key of ['job_types', 'tasks', 'supported_job_types'] as const) {
    const value = capabilities[key];
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (typeof item === 'string' && item && !declared.includes(item)) declared.push(item);
      });
    }
  }
  if (capabilities.xhs === true) {
    ['feed_collect', 'creator_monitor'].forEach((item) => {
      if (!declared.includes(item)) declared.push(item);
    });
  }
  return declared;
}

export function agentCapabilityKind(capabilities?: Record<string, unknown> | null): 'runtime_v1' | 'legacy' | 'unknown' {
  if (capabilities?.runtime === 'local_agent_runtime_v1') return 'runtime_v1';
  if (capabilities?.runner || capabilities?.probe) return 'legacy';
  if (listDeclaredJobTypes(capabilities).length) return 'runtime_v1';
  return 'unknown';
}

export function supportsAccountLogin(capabilities?: Record<string, unknown> | null): boolean {
  return capabilities?.supports_account_login === true;
}

const HEARTBEAT_ONLINE_MS = 90_000;

function parseHeartbeatMs(value: string): number {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  return Date.parse(hasTz ? value : `${value}Z`);
}

export function isAgentLive(agent: { status?: string; last_heartbeat_at?: string | null }): boolean {
  if (agent.status === 'retired' || agent.status === 'offline') return false;
  if (!agent.last_heartbeat_at) return false;
  const age = Date.now() - parseHeartbeatMs(agent.last_heartbeat_at);
  if (Number.isNaN(age)) return false;
  return age < HEARTBEAT_ONLINE_MS;
}

export function sortAgentsForDisplay<T extends { status?: string; last_heartbeat_at?: string | null; capabilities?: Record<string, unknown> | null }>(
  agents: T[],
): T[] {
  return [...agents].sort((left, right) => {
    const leftKey = [
      left.status === 'retired' ? 1 : 0,
      isAgentLive(left) ? 0 : 1,
      supportsAccountLogin(left.capabilities) ? 0 : 1,
      -(left.last_heartbeat_at ? Date.parse(left.last_heartbeat_at) : 0),
    ];
    const rightKey = [
      right.status === 'retired' ? 1 : 0,
      isAgentLive(right) ? 0 : 1,
      supportsAccountLogin(right.capabilities) ? 0 : 1,
      -(right.last_heartbeat_at ? Date.parse(right.last_heartbeat_at) : 0),
    ];
    for (let index = 0; index < leftKey.length; index += 1) {
      if (leftKey[index] !== rightKey[index]) return leftKey[index] - rightKey[index];
    }
    return 0;
  });
}

export function pickPreferredAgent<T extends {
  id: string;
  employee_id?: string | null;
  status?: string;
  last_heartbeat_at?: string | null;
  capabilities?: Record<string, unknown> | null;
}>(agents: T[], employeeId?: string | null): T | undefined {
  const sorted = sortAgentsForDisplay(agents);
  const scoped = employeeId ? sorted.filter((item) => item.employee_id === employeeId) : sorted;
  const pool = scoped.length ? scoped : sorted;
  const loginCapable = pool.filter((item) => supportsAccountLogin(item.capabilities));
  const liveLogin = loginCapable.filter((item) => isAgentLive(item));
  return liveLogin[0] || loginCapable.find((item) => isAgentLive(item)) || loginCapable[0] || pool.find((item) => isAgentLive(item)) || pool[0];
}

export function formatAgentOptionLabel(agent: {
  id: string;
  device_name?: string | null;
  employee_display_name?: string | null;
  status?: string;
  last_heartbeat_at?: string | null;
  machine_fingerprint?: string | null;
  login_cdp_port?: number | null;
}): string {
  const name = formatAgentDeviceLabel(agent);
  const live = isAgentLive(agent);
  const heartbeat = live ? formatAgentHeartbeat(agent) : '暂无心跳';
  const owner = agent.employee_display_name || '未绑定员工';
  const cdp = agent.login_cdp_port ? ` · CDP :${agent.login_cdp_port}` : '';
  const suffix = agent.machine_fingerprint ? ` · ${agent.machine_fingerprint.slice(-6)}` : ` · ${agent.id.slice(0, 8)}`;
  return `${name} · ${live ? '在线' : '离线'} · ${owner}${cdp} · ${heartbeat}${suffix}`;
}

export function formatAgentHeartbeat(agent: { last_heartbeat_at?: string | null }): string {
  if (!agent.last_heartbeat_at) return '暂无心跳';
  const when = parseHeartbeatMs(agent.last_heartbeat_at);
  if (Number.isNaN(when)) return '暂无心跳';
  const ageMs = Date.now() - when;
  const local = new Date(when).toLocaleString('zh-CN', { hour12: false });
  if (ageMs < 60_000) return `${local}（刚刚）`;
  if (ageMs < 3_600_000) return `${local}（${Math.floor(ageMs / 60_000)} 分钟前）`;
  if (ageMs < 86_400_000) return `${local}（${Math.floor(ageMs / 3_600_000)} 小时前）`;
  return local;
}

export function formatAgentDeviceLabel(agent: { id: string; device_name?: string | null }): string {
  const name = agent.device_name || '未命名设备';
  if (name.includes(agent.id.slice(0, 8))) return name;
  return `${name} (${agent.id.slice(0, 8)})`;
}

export function formatAgentCapabilities(capabilities?: Record<string, unknown> | null): string {
  const jobTypes = listDeclaredJobTypes(capabilities);
  if (jobTypes.length) {
    const runtime = typeof capabilities?.runtime === 'string' ? capabilities.runtime : 'local_agent_runtime_v1';
    return `${runtime} · ${jobTypes.join(', ')}`;
  }
  const runner = typeof capabilities?.runner === 'string' ? capabilities.runner : '';
  const probe = typeof capabilities?.probe === 'string' ? capabilities.probe : '';
  if (runner) return `legacy runner: ${runner}`;
  if (probe) return `legacy probe: ${probe}`;
  return '未声明 job_types';
}
