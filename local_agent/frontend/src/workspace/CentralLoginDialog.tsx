import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../ui/ToastContext';
import type { CentralSession } from '../types';

interface Props {
  open: boolean;
  defaultCenterUrl: string;
  onClose: () => void;
  onSuccess: (session: CentralSession) => void;
}

export function CentralLoginDialog({ open, defaultCenterUrl, onClose, onSuccess }: Props) {
  const toast = useToast();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [centerUrl, setCenterUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setCenterUrl(defaultCenterUrl);
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open, defaultCenterUrl]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const session = await api<CentralSession>('/api/local/central-session/login', {
        method: 'POST',
        body: JSON.stringify({ center_url: centerUrl.trim(), username: username.trim(), password }),
      });
      setPassword('');
      onSuccess(session);
    } catch (error) {
      setPassword('');
      toast((error as Error).message);
    }
  };

  return (
    <dialog ref={dialogRef} onCancel={onClose}>
      <form className="dialog-form" onSubmit={submit}>
        <div className="dialog-heading">
          <h2>登录中央素材库</h2>
          <button className="icon-close" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>
        <label htmlFor="centralServerUrl">中央服务地址</label>
        <input
          id="centralServerUrl"
          type="url"
          placeholder="https://operations.company.com"
          autoComplete="url"
          required
          value={centerUrl}
          onChange={(event) => setCenterUrl(event.target.value)}
        />
        <label htmlFor="centralUsername">用户名</label>
        <input
          id="centralUsername"
          autoComplete="username"
          required
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
        <label htmlFor="centralPassword">密码</label>
        <input
          id="centralPassword"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <button type="submit">登录</button>
      </form>
    </dialog>
  );
}
