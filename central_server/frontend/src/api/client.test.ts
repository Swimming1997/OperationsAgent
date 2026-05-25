import { describe, expect, it, vi } from 'vitest';
import { apiRequest } from './client';

describe('apiRequest', () => {
  it('injects development auth headers', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/api/test', { role: 'supervisor', userId: 'u-1' });

    expect(fetchMock).toHaveBeenCalledWith('/api/test', expect.objectContaining({
      headers: expect.objectContaining({ 'X-Role': 'supervisor', 'X-User-Id': 'u-1' }),
    }));
  });

  it('maps 403 to a readable error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403 })));

    await expect(apiRequest('/api/forbidden', { role: 'operator' })).rejects.toThrow('无权限');
  });
});
