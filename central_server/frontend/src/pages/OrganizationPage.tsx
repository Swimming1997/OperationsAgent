import { useCallback, useEffect, useState } from 'react';
import { listEmployees, listUsers, type OrgEmployee, type OrgUser } from '../api/organization';
import { ErrorState, LoadingState } from '../components/Status';
import type { Role } from '../types/api';
import { EmployeesTab } from './organization/EmployeesTab';
import { UsersTab } from './organization/UsersTab';

type Tab = 'employees' | 'users';

type Props = {
  role: Role;
  userId: string;
};

export function OrganizationPage({ role, userId }: Props) {
  const [tab, setTab] = useState<Tab>('employees');
  const [users, setUsers] = useState<OrgUser[]>([]);
  const [employees, setEmployees] = useState<OrgEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [nextUsers, nextEmployees] = await Promise.all([listUsers(role, userId), listEmployees(role, userId)]);
      setUsers(nextUsers);
      setEmployees(nextEmployees);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [role, userId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <section className="page-grid org-page" data-testid="organization-page">
      <header className="org-page-header">
        <div>
          <h1>组织管理</h1>
          <p className="ops-intro">
            管理系统用户、员工档案与角色权限。主管可在此创建员工账号并分配登录权限。
          </p>
        </div>
        {toast ? <span className="toast">{toast}</span> : null}
      </header>

      <div className="org-tabs" role="tablist" aria-label="组织管理">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'employees'}
          className={`org-tab ${tab === 'employees' ? 'active' : ''}`}
          onClick={() => setTab('employees')}
        >
          员工管理
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'users'}
          className={`org-tab ${tab === 'users' ? 'active' : ''}`}
          onClick={() => setTab('users')}
        >
          用户管理
        </button>
      </div>

      <div className="org-body">
        {loading ? <LoadingState text="组织数据加载中" /> : null}
        {error ? <ErrorState text={error} /> : null}
        {!loading && !error && tab === 'employees' ? (
          <EmployeesTab
            employees={employees}
            users={users}
            role={role}
            userId={userId}
            onChanged={(message) => {
              setToast(message);
              void reload();
            }}
          />
        ) : null}
        {!loading && !error && tab === 'users' ? (
          <UsersTab
            users={users}
            role={role}
            userId={userId}
            onChanged={(message) => {
              setToast(message);
              void reload();
            }}
          />
        ) : null}
      </div>
    </section>
  );
}
