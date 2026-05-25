import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { installFetchMock } from '../test/serverMock';
import { AccountsPage } from './AccountsPage';
import { AgentsPage } from './AgentsPage';
import { BenchmarksPage } from './BenchmarksPage';
import { RulesPage } from './RulesPage';

describe('resource configuration pages', () => {
  it('renders account list and detail editor', async () => {
    installFetchMock();
    render(
      <AuthProvider>
        <AccountsPage role="supervisor" userId="supervisor-user" />
      </AuthProvider>,
    );
    expect(await screen.findByText('小红书测试账号')).toBeInTheDocument();
    expect(screen.getAllByText('业务账号类型').length).toBeGreaterThan(0);
  });

  it('operator loads accounts without business-type permission error', async () => {
    installFetchMock({
      authUserId: 'operator-user',
      authUsername: 'operator',
      authDisplayName: '运营一组',
      authRoles: ['operator'],
      authEmployeeId: 'employee-1',
    });
    render(
      <AuthProvider>
        <AccountsPage role="operator" userId="operator-user" />
      </AuthProvider>,
    );
    expect(await screen.findByText('小红书测试账号')).toBeInTheDocument();
    expect(screen.queryByText('无权限访问当前资源')).not.toBeInTheDocument();
    expect(screen.getByText('本地 Agent 已连接')).toBeInTheDocument();
    expect(screen.getByText(/选择左侧账号查看详情/)).toBeInTheDocument();
  });

  it('operator can open create form from header button', async () => {
    installFetchMock({
      authUserId: 'operator-user',
      authUsername: 'operator',
      authDisplayName: '运营一组',
      authRoles: ['operator'],
      authEmployeeId: 'employee-1',
    });
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <AccountsPage role="operator" userId="operator-user" />
      </AuthProvider>,
    );
    await screen.findByText('小红书测试账号');
    await user.click(screen.getByRole('button', { name: '添加运营账号' }));
    const createBtn = screen.getByRole('button', { name: '创建账号' });
    expect(createBtn).toBeDisabled();
    await user.type(screen.getByPlaceholderText('如：XHS-账号A'), 'XHS-新账号');
    expect(createBtn).toBeEnabled();
    const platformSelect = document.querySelector('.detail-panel-create select') as HTMLSelectElement;
    expect(platformSelect?.value).toBe('xhs');
  });

  it('renders benchmark members and business type binding', async () => {
    installFetchMock();
    render(<BenchmarksPage role="supervisor" userId="supervisor-user" />);
    expect(await screen.findByText('SCI 对标组')).toBeInTheDocument();
    expect(await screen.findByText('对标作者')).toBeInTheDocument();
    expect(await screen.findByText('论文服务号')).toBeInTheDocument();
  });

  it('renders rules and switches to keyword rules', async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<RulesPage role="supervisor" userId="supervisor-user" />);
    expect(await screen.findByText('SCI 关键词')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关键词规则' }));
    expect(await screen.findByText('SCI')).toBeInTheDocument();
  });

  it('renders agent list and detail', async () => {
    installFetchMock();
    render(<AgentsPage role="supervisor" userId="supervisor-user" />);
    expect((await screen.findAllByText(/WIN-AGENT/)).length).toBeGreaterThan(0);
    expect(await screen.findByText('Capabilities')).toBeInTheDocument();
  });

  it('shows permission error state when API returns 403', async () => {
    installFetchMock();
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/auth/')) {
        return new Response(
          JSON.stringify({
            id: 'operator-user',
            username: 'operator',
            display_name: '运营',
            email: null,
            status: 'active',
            roles: ['operator'],
            employee_id: 'employee-1',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403, headers: { 'Content-Type': 'application/json' } });
    });
    render(
      <AuthProvider>
        <AccountsPage role="operator" userId="operator-user" />
      </AuthProvider>,
    );
    expect(await screen.findByText('无权限访问当前资源')).toBeInTheDocument();
  });
});
