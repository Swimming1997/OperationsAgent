import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { TasksPage } from './TasksPage';

describe('TasksPage', () => {
  it('renders task list and switches resource selectors by task type', async () => {
    installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);

    expect(await screen.findByText('推荐流巡检')).toBeInTheDocument();
    expect(screen.getByLabelText('模板类型')).toBeInTheDocument();
    expect(await screen.findByTestId('executor-account-select')).toHaveTextContent('小红书测试账号');
    await user.selectOptions(screen.getByLabelText('模板类型'), 'creator_monitor_task');
    expect(await screen.findByTestId('benchmark-group-select')).toBeInTheDocument();
    expect(screen.queryByTestId('rule-set-select')).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('模板类型'), 'keyword_search_task');
    expect(await screen.findByText('关键词')).toBeInTheDocument();
    expect(screen.getByTestId('rule-set-select')).toBeInTheDocument();
  });

  it('runs selected task template', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await user.click(await screen.findByText('推荐流巡检'));
    await user.click(screen.getByRole('button', { name: /立即运行/ }));

    await waitFor(() => expect(requests.some((request) => request.url.includes('/task-1/run'))).toBe(true));
    expect(await screen.findByText(/已创建 1 个 Job/)).toBeInTheDocument();
    expect(await screen.findByTestId('task-run-panel')).toHaveTextContent('任务执行成功，本次采样 10 条，新增 0 条');
    expect(await screen.findByTestId('recent-runs')).toBeInTheDocument();
  });

  it('renders readiness blockers and disables manual run when agent is not ready', async () => {
    installFetchMock({ blockedReadiness: true });
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await user.click(await screen.findByText('推荐流巡检'));

    expect(await screen.findByTestId('readiness-card')).toHaveTextContent('当前不可运行');
    expect(screen.getByTestId('readiness-card')).toHaveTextContent('绑定 Agent 当前离线');
    expect(screen.getByRole('button', { name: /立即运行/ })).toBeDisabled();
  });

  it('submits selected resource ids when saving', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('推荐流巡检');
    await user.selectOptions(screen.getByTestId('executor-account-select'), 'account-1');
    await user.selectOptions(screen.getByTestId('rule-set-select'), 'rule-set-1');
    await user.click(screen.getByRole('button', { name: /保存/ }));

    await waitFor(() => expect(requests.some((request) => request.url.includes('/recommendation-feed'))).toBe(true));
    const saveRequest = requests.find((request) => request.url.includes('/recommendation-feed'));
    expect(saveRequest?.init?.body).toContain('account-1');
    expect(saveRequest?.init?.body).toContain('rule-set-1');
  });
});
