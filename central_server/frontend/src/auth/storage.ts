const TOKEN_KEY = 'amiracle_access_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function isDevAuthEnabled(): boolean {
  return localStorage.getItem('amiracle_dev_auth') === '1';
}

export function setDevAuthEnabled(enabled: boolean) {
  if (enabled) {
    localStorage.setItem('amiracle_dev_auth', '1');
  } else {
    localStorage.removeItem('amiracle_dev_auth');
  }
}
