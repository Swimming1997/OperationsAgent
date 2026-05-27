import { useState } from 'react';
import { performLogin, performRegister } from '../auth/AuthContext';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { completeLogin } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (mode === 'register' && password !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }
    if (mode === 'register' && password.length < 8) {
      setError('密码至少 8 位');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const user = mode === 'login'
        ? await performLogin(username.trim(), password)
        : await performRegister({
            username: username.trim(),
            display_name: displayName.trim(),
            email: email.trim() || undefined,
            password,
          });
      completeLogin(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : mode === 'login' ? '登录失败' : '注册失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-screen" data-testid="login-page">
      <form className="auth-card" onSubmit={(event) => void onSubmit(event)}>
        <h1>运营情报中心</h1>
        <p className="auth-sub">请使用管理员或员工账号登录</p>
        <div className="auth-mode-tabs" role="tablist" aria-label="账号操作">
          <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>
            登录
          </button>
          <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>
            注册
          </button>
        </div>
        <label htmlFor="login-username">用户名</label>
        <input id="login-username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
        {mode === 'register' ? (
          <>
            <label htmlFor="register-display-name">显示名</label>
            <input id="register-display-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
            <label htmlFor="register-email">邮箱（可选）</label>
            <input id="register-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </>
        ) : null}
        <label htmlFor="login-password">密码</label>
        <input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required />
        {mode === 'register' ? (
          <>
            <label htmlFor="register-confirm-password">确认密码</label>
            <input id="register-confirm-password" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" required />
          </>
        ) : null}
        {error ? <p className="inline-error">{error}</p> : null}
        <button type="submit" disabled={loading}>{loading ? (mode === 'login' ? '登录中…' : '注册中…') : (mode === 'login' ? '登录' : '注册并进入系统')}</button>
      </form>
    </div>
  );
}
