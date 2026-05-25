import { useState } from 'react';
import { performBootstrapAdmin, useAuth } from '../auth/AuthContext';

export function BootstrapAdminPage() {
  const { completeLogin } = useAuth();
  const [username, setUsername] = useState('admin');
  const [displayName, setDisplayName] = useState('系统管理员');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const user = await performBootstrapAdmin({
        username: username.trim(),
        display_name: displayName.trim(),
        email: email.trim() || undefined,
        password,
      });
      completeLogin(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : '初始化失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-screen" data-testid="bootstrap-admin-page">
      <form className="auth-card" onSubmit={(event) => void onSubmit(event)}>
        <h1>初始化管理员</h1>
        <p className="auth-sub">系统尚无用户，请先创建第一个管理员账号。</p>
        <label>用户名</label>
        <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        <label>显示名</label>
        <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
        <label>邮箱（可选）</label>
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <label>密码</label>
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        <label>确认密码</label>
        <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
        {error ? <p className="inline-error">{error}</p> : null}
        <button type="submit" disabled={loading}>{loading ? '创建中…' : '创建并进入系统'}</button>
      </form>
    </div>
  );
}
