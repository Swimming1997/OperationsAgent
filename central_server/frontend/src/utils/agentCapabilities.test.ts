import { describe, expect, it } from 'vitest';
import { formatAgentOptionLabel, isAgentLive, pickPreferredAgent } from './agentCapabilities';

describe('agentCapabilities', () => {
  it('treats explicit offline status as not live even with recent heartbeat', () => {
    const agent = {
      id: 'a1',
      status: 'offline',
      last_heartbeat_at: new Date().toISOString(),
      capabilities: { supports_account_login: true },
    };
    expect(isAgentLive(agent)).toBe(false);
  });

  it('treats recent heartbeat as live when status is online', () => {
    const agent = {
      id: 'a1',
      status: 'online',
      last_heartbeat_at: new Date().toISOString(),
      capabilities: { supports_account_login: true },
    };
    expect(isAgentLive(agent)).toBe(true);
  });

  it('prefers live login-capable agent owned by employee', () => {
    const chosen = pickPreferredAgent(
      [
        {
          id: 'stale',
          employee_id: 'emp-1',
          device_name: 'WIN-1',
          status: 'offline',
          last_heartbeat_at: null,
          capabilities: {},
        },
        {
          id: 'live',
          employee_id: 'emp-1',
          device_name: 'WIN-1',
          status: 'online',
          last_heartbeat_at: new Date().toISOString(),
          capabilities: { supports_account_login: true },
        },
      ],
      'emp-1',
    );
    expect(chosen?.id).toBe('live');
  });

  it('formats option label with owner and heartbeat', () => {
    const label = formatAgentOptionLabel({
      id: 'live',
      device_name: 'WIN-1',
      employee_display_name: '范贤亮',
      status: 'online',
      last_heartbeat_at: new Date().toISOString(),
      machine_fingerprint: 'demo-fingerprint',
    });
    expect(label).toContain('WIN-1');
    expect(label).toContain('范贤亮');
    expect(label).toContain('在线');
  });
});
