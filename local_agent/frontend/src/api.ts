import { getBridgeToken } from './bridge';

export async function api<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getBridgeToken();
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = (payload as { detail?: string })?.detail;
    throw new Error(detail || `请求失败 ${response.status}`);
  }
  return payload as T;
}
