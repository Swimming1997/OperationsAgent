// The bridge token arrives in the URL hash fragment. We keep it ONLY in this
// in-memory module variable (never persisted to any browser storage) and scrub
// it from the address bar after establishing the session cookie.
const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''));
const bridgeToken = fragment.get('token') || '';

export function getBridgeToken(): string {
  return bridgeToken;
}

export async function establishBridgeSession(): Promise<void> {
  if (!bridgeToken) return;
  const response = await fetch('/bridge/session', {
    method: 'POST',
    headers: { Authorization: `Bearer ${bridgeToken}` },
  });
  if (!response.ok) {
    throw new Error('本地工作台鉴权失败，请重新复制启动日志中的地址');
  }
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
}
