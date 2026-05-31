import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { operationsSummary } from '../test/operationsMockData';
import { OperationsPage } from './OperationsPage';

describe('OperationsPage', () => {
  it('shows collection quality panel for supervisor', async () => {
    installFetchMock();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);
    expect(await screen.findByTestId('collection-quality-panel')).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /展开采集质量/ }));
    expect(await screen.findByText('今日新增内容')).toBeInTheDocument();
  });

  it('hides collection quality panel for operator', async () => {
    installFetchMock();
    render(<OperationsPage role="operator" userId="operator-user" />);
    await screen.findByTestId('ops-overview');
    expect(screen.queryByTestId('collection-quality-panel')).not.toBeInTheDocument();
  });

  it('uses the new filter-list-detail operations layout', async () => {
    installFetchMock({
      orgEmployees: [
        { id: 'employee-supervisor', user_id: 'supervisor-user', display_name: '演示主管', email: null, status: 'active', user_username: 'supervisor', account_count: 0, agent_count: 0 },
        { id: 'employee-operator', user_id: 'operator-user', display_name: '运营一组', email: null, status: 'active', user_username: 'operator', account_count: 0, agent_count: 0 },
      ],
    });
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    expect(await screen.findByTestId('ops-filter-panel')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态筛选')).toHaveDisplayValue('全部状态');
    expect(screen.getByRole('option', { name: '待处理' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '进行中' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '已完成' })).toBeInTheDocument();
    expect(screen.getByLabelText('仅看执行超时')).toBeInTheDocument();
    expect((await screen.findAllByText('任务运行记录')).length).toBeGreaterThan(0);
    expect(await screen.findByText('运行详情')).toBeInTheDocument();
    expect(screen.getByText('任务结论')).toBeInTheDocument();
    expect(screen.getByTestId('ops-pagination')).toBeInTheDocument();
    expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument();
    expect(screen.queryByText('如何使用运行中心？')).not.toBeInTheDocument();
    expect(screen.queryByText('返回任务模板')).not.toBeInTheDocument();
    expect(screen.queryByText('高级排障筛选')).not.toBeInTheDocument();
    expect(screen.queryByText('仅独立补采')).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('负责人筛选'), 'employee-operator');
    expect((await screen.findAllByText('推荐页巡检')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('手动补采')).length).toBeGreaterThan(0);

    await user.selectOptions(screen.getByLabelText('负责人筛选'), 'employee-supervisor');
    expect(await screen.findByText('暂无符合条件的任务运行记录')).toBeInTheDocument();
  });

  it('applies stale-only filter from the main filter panel', async () => {
    installFetchMock();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);
    const user = userEvent.setup();
    await screen.findByTestId('ops-filter-panel');

    await user.click(screen.getByLabelText('仅看执行超时'));
    expect(await screen.findByText('采集步骤执行超时，可能需要释放后重试')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态筛选')).toHaveDisplayValue('待处理');
  });

  it('shows orphan warning card without navigation action', async () => {
    installFetchMock({
      operationsSummary: {
        ...operationsSummary,
        orphan_active_job_count: 2,
      },
    });
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    expect(await screen.findByTestId('ops-orphan-warning-card')).toBeInTheDocument();
    expect(screen.getByText('异常残留任务')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /异常残留任务/ })).not.toBeInTheDocument();
  });
});
