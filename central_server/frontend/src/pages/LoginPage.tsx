import { useState } from 'react';
import { performLogin } from '../auth/AuthContext';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { completeLogin } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const user = await performLogin(username.trim(), password);
      completeLogin(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-screen" data-testid="login-page">
      <form className="auth-card" onSubmit={(event) => void onSubmit(event)}>
        <h1>运营情报中心</h1>
        <p className="auth-sub">请使用管理员或员工账号登录</p>
        <label htmlFor="login-username">用户名</label>
        <input id="login-username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
        <label htmlFor="login-password">密码</label>
        <input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
        {error ? <p className="inline-error">{error}</p> : null}
        <button type="submit" disabled={loading}>{loading ? '登录中…' : '登录'}</button>
      </form>
    </div>
  );
}
