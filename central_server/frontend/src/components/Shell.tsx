import {
  Activity,
  BarChart3,
  Building2,
  ClipboardList,
  Database,
  MonitorCog,
  ShieldCheck,
  UsersRound,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { canAccessRoute } from '../utils/roleLabels';
import { labelRole } from '../utils/roleLabels';
import type { Role } from '../types/api';

type Props = {
  activeRoute: string;
  onRouteChange: (route: string) => void;
  children: ReactNode;
};

const navItems = [
  { route: 'intelligence', label: '情报中心', icon: Database },
  { route: 'tasks', label: '情报任务中心', icon: ClipboardList },
  { route: 'operations', label: '运行中心', icon: Activity },
  { route: 'accounts', label: '账号管理', icon: UsersRound },
  { route: 'benchmarks', label: '对标账号管理', icon: BarChart3 },
  { route: 'rules', label: '规则管理', icon: ShieldCheck },
  { route: 'agents', label: 'Agent 管理', icon: MonitorCog },
  { route: 'organization', label: '组织管理', icon: Building2 },
];

export function Shell({ activeRoute, onRouteChange, children }: Props) {
  const auth = useAuth();
  const [showDevTools, setShowDevTools] = useState(false);
  const visibleNav = navItems.filter((item) => canAccessRoute(item.route, auth.roles));

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="system-name">运营情报中心</div>
          <div className="system-sub">Intelligence Operations Console</div>
        </div>
        <div className="identity-panel" data-testid="current-user-panel">
          {auth.user ? (
            <>
              <span className="user-display">{auth.user.display_name}</span>
              <span className="user-role-tag">{auth.roles.map(labelRole).join(' / ')}</span>
            </>
          ) : (
            <span className="user-display">开发模式</span>
          )}
          <button type="button" className="secondary" onClick={() => void auth.logout()}>退出登录</button>
          <button type="button" className="ghost" onClick={() => setShowDevTools((value) => !value)} title="开发工具">
            开发
          </button>
        </div>
      </header>

      {showDevTools ? (
        <div className="dev-tools" data-testid="dev-auth-tools">
          <label>
            <input type="checkbox" checked={auth.devAuth} onChange={(event) => auth.setDevAuth(event.target.checked)} />
            使用 Header 模拟身份（仅开发）
          </label>
          {auth.devAuth ? (
            <>
              <select
                value={auth.role}
                onChange={(event) => auth.setDevIdentity(event.target.value as Role, auth.userId)}
                aria-label="开发角色"
              >
                <option value="admin">admin</option>
                <option value="supervisor">supervisor</option>
                <option value="operator">operator</option>
                <option value="sales">sales</option>
              </select>
              <code>{auth.userId}</code>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="workspace">
        <aside className="sidebar">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.route}
                className={`nav-item ${activeRoute === item.route ? 'active' : ''}`}
                onClick={() => onRouteChange(item.route)}
                title={item.label}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </aside>
        <main className="main-surface">{children}</main>
      </div>
    </div>
  );
}
