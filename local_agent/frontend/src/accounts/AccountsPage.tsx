import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../ui/ToastContext';
import { authStatusLabel, platformLabel } from '../utils';
import type { AccountListResponse, PlatformAccount } from '../types';

interface Props {
  refreshSignal: number;
}

export function AccountsPage({ refreshSignal }: Props) {
  const toast = useToast();
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [platform, setPlatform] = useState('xhs');
  const [displayName, setDisplayName] = useState('');
  const [adding, setAdding] = useState(false);
  const pollingRef = useRef<Set<string>>(new Set());

  const load = useCallback(async () => {
    const data = await api<AccountListResponse>('/api/local/accounts');
    setAccounts(data.items);
  }, []);

  useEffect(() => {
    load().catch((error: Error) => toast(error.message));
  }, [load, toast, refreshSignal]);

  const pollLogin = useCallback(
    async (accountId: string, attempts = 0) => {
      if (attempts > 80) {
        pollingRef.current.delete(accountId);
        return;
      }
      try {
        const account = await api<PlatformAccount>(`/api/local/accounts/${accountId}`);
        setAccounts((prev) => prev.map((item) => (item.id === accountId ? account : item)));
        if (account.auth_status !== 'login_pending') {
          pollingRef.current.delete(accountId);
          toast(account.auth_status === 'active' ? '账号登录成功' : '登录未完成，请重试');
          return;
        }
      } catch {
        /* keep polling */
      }
      window.setTimeout(() => pollLogin(accountId, attempts + 1), 8000);
    },
    [toast],
  );

  const addAccount = async (event: React.FormEvent) => {
    event.preventDefault();
    setAdding(true);
    try {
      await api('/api/local/accounts', {
        method: 'POST',
        body: JSON.stringify({ platform, display_name: displayName.trim() }),
      });
      setDisplayName('');
      await load();
      toast('账号已添加');
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setAdding(false);
    }
  };

  const startLogin = async (accountId: string) => {
    try {
      await api(`/api/local/accounts/${accountId}/login`, { method: 'POST', body: '{}' });
      toast('已打开浏览器，请在窗口里完成登录');
      await load();
      if (!pollingRef.current.has(accountId)) {
        pollingRef.current.add(accountId);
        pollLogin(accountId);
      }
    } catch (error) {
      toast((error as Error).message);
    }
  };

  const deleteAccount = async (accountId: string) => {
    try {
      await api(`/api/local/accounts/${accountId}/delete`, { method: 'POST', body: '{}' });
      await load();
      toast('账号已删除');
    } catch (error) {
      toast((error as Error).message);
    }
  };

  return (
    <div className="accounts-page">
      <h2>账号管理</h2>
      <p className="account-hint">
        在这台电脑上管理你的小红书 / 抖音账号。添加后点“登录”，会打开一个独立浏览器窗口；在窗口里完成登录后，状态会自动变为“已登录”。账号与登录态都保存在本机，中央只做监控。
      </p>

      <form className="account-add-row" onSubmit={addAccount}>
        <select aria-label="平台" value={platform} onChange={(event) => setPlatform(event.target.value)}>
          <option value="xhs">小红书</option>
          <option value="douyin">抖音</option>
        </select>
        <input
          type="text"
          placeholder="账号备注名（可选）"
          autoComplete="off"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />
        <button type="submit" disabled={adding}>
          添加账号
        </button>
      </form>

      <div className="account-list">
        {accounts.length === 0 && <span className="account-empty">还没有账号，先在上方添加。</span>}
        {accounts.map((account) => {
          const name = account.platform_nickname || account.display_name || '未命名账号';
          const pending = account.auth_status === 'login_pending';
          const loginLabel = pending ? '登录中…' : account.auth_status === 'active' ? '重新登录' : '登录';
          return (
            <div className="account-row" key={account.id}>
              <div className="account-main">
                <span className={`account-platform account-platform-${account.platform}`}>
                  {platformLabel(account.platform)}
                </span>
                <div className="account-copy">
                  <strong>{name}</strong>
                  <span className={`account-badge account-${account.auth_status}`}>
                    {authStatusLabel(account.auth_status)}
                  </span>
                </div>
              </div>
              <div className="account-actions">
                <button className="secondary" type="button" disabled={pending} onClick={() => startLogin(account.id)}>
                  {loginLabel}
                </button>
                <button className="danger-outline" type="button" onClick={() => deleteAccount(account.id)}>
                  删除
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
