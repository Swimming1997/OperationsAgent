import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { OrganizationPage } from './OrganizationPage';

const mockUsers = [
  {
    id: 'supervisor-user',
    username: 'supervisor',
    display_name: '演示主管',
    email: 'boss@example.com',
    status: 'active',
    roles: ['supervisor'],
    created_at: '2026-01-01T00:00:00Z',
    employee_id: null,
  },
];

const mockEmployees = [
  {
    id: 'employee-1',
    user_id: 'operator-user',
    display_name: '运营一组',
    email: 'op@example.com',
    status: 'active',
    user_username: 'operator',
    user_display_name: '运营员工',
    account_count: 2,
    agent_count: 1,
  },
];

describe('OrganizationPage', () => {
  it('renders employees tab with table and no light-theme tab blocks', async () => {
    installFetchMock({ orgUsers: mockUsers, orgEmployees: [] });
    const { container } = render(<OrganizationPage role="supervisor" userId="supervisor-user" />);

    expect(await screen.findByTestId('organization-page')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '员工管理' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('employees-panel')).toBeInTheDocument();
    expect(screen.getByTestId('employees-empty')).toHaveTextContent('暂无员工');
    expect(container.querySelector('.tab-row')).toBeNull();
    expect(container.querySelector('.form-card')).toBeNull();
  });

  it('switches to users tab and shows admin user', async () => {
    installFetchMock({ orgUsers: mockUsers, orgEmployees: mockEmployees });
    const user = userEvent.setup();
    render(<OrganizationPage role="supervisor" userId="supervisor-user" />);

    await user.click(await screen.findByRole('tab', { name: '用户管理' }));
    expect(screen.getByTestId('users-panel')).toBeInTheDocument();
    expect(await screen.findByText('supervisor')).toBeInTheDocument();
    expect(screen.getByText('演示主管')).toBeInTheDocument();
  });

  it('opens create employee panel from toolbar', async () => {
    installFetchMock({ orgUsers: mockUsers, orgEmployees: mockEmployees });
    const user = userEvent.setup();
    render(<OrganizationPage role="supervisor" userId="supervisor-user" />);

    await screen.findByText('运营一组');
    await user.click(screen.getByRole('button', { name: '创建员工账号' }));
    expect(screen.getByText('创建员工账号', { selector: '.panel-title' })).toBeInTheDocument();
    expect(screen.getByText('初始密码')).toBeInTheDocument();
  });

  it('shows employee detail when row clicked', async () => {
    installFetchMock({ orgUsers: mockUsers, orgEmployees: mockEmployees });
    const user = userEvent.setup();
    render(<OrganizationPage role="supervisor" userId="supervisor-user" />);

    await user.click(await screen.findByText('运营一组'));
    expect(screen.getByText('员工详情 / 编辑')).toBeInTheDocument();
    expect(screen.getByText('负责账号数：2')).toBeInTheDocument();
  });
});
