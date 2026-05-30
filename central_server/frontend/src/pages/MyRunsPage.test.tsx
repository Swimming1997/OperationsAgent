import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TaskRunRefreshProvider } from '../context/TaskRunRefreshContext';
import { installFetchMock } from '../test/serverMock';
import { MyRunsPage } from './MyRunsPage';

const useAuthMock = vi.fn();

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => useAuthMock(),
}));

function renderMyRuns(props: { initialTaskRunId?: string } = {}) {
  useAuthMock.mockReturnValue({
    employeeId: 'employee-operator',
    phase: 'authenticated',
    role: 'operator',
    userId: 'operator-user',
    roles: ['operator'],
  });
  return render(
    <TaskRunRefreshProvider role="operator" userId="operator-user" employeeId="employee-operator">
      <MyRunsPage role="operator" userId="operator-user" {...props} />
    </TaskRunRefreshProvider>,
  );
}

describe('MyRunsPage', () => {
  beforeEach(() => {
    installFetchMock();
  });

  it('renders scoped run list and detail panel', async () => {
    renderMyRuns();
    expect(await screen.findByTestId('my-runs-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '我的运行' })).toBeInTheDocument();
    expect(await screen.findByText('推荐页巡检')).toBeInTheDocument();
    expect(await screen.findByTestId('run-detail-panel')).toBeInTheDocument();
    expect(screen.getByLabelText('执行账号筛选')).toBeInTheDocument();
  });

  it('opens deep-linked task run', async () => {
    renderMyRuns({ initialTaskRunId: 'run-1' });
    expect(await screen.findByTestId('run-detail-panel')).toBeInTheDocument();
  });

  it('shows message when operator has no employee profile', async () => {
    useAuthMock.mockReturnValue({
      employeeId: null,
      phase: 'authenticated',
      role: 'operator',
      userId: 'operator-user',
      roles: ['operator'],
    });
    render(
      <TaskRunRefreshProvider role="operator" userId="operator-user" employeeId={null}>
        <MyRunsPage role="operator" userId="operator-user" />
      </TaskRunRefreshProvider>,
    );
    expect(await screen.findByTestId('my-runs-no-employee')).toBeInTheDocument();
  });

  it('filters by account selection', async () => {
    renderMyRuns();
    const user = userEvent.setup();
    await screen.findByText('推荐页巡检');
    const accountFilter = screen.getByLabelText('执行账号筛选');
    await user.selectOptions(accountFilter, 'account-1');
    expect(accountFilter).toHaveDisplayValue('小红书测试账号');
  });
});
