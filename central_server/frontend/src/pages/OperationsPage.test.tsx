import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { OperationsPage } from './OperationsPage';

describe('OperationsPage', () => {
  it('renders localized overview cards and help', async () => {
    installFetchMock();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    expect(await screen.findByText('运行批次概览')).toBeInTheDocument();
    expect(screen.getByText('执行项概览')).toBeInTheDocument();
    expect(screen.getByTestId('task-run-summary')).toHaveTextContent('已完成');
    expect(screen.getByTestId('queue-summary')).toHaveTextContent('超时未结束');
    expect(screen.getByTestId('queue-summary')).toHaveTextContent('历史遗留待执行');
    expect(screen.getByTestId('queue-summary')).toHaveTextContent('执行中');
    expect(screen.getByTestId('ops-help')).toHaveTextContent('如何使用运行中心');
  });

  it('renders admin action buttons with clear Chinese labels', async () => {
    installFetchMock();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    expect(await screen.findByRole('button', { name: '处理超时执行项' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看历史遗留待执行项' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '取消历史遗留待执行项' })).toBeInTheDocument();
  });

  it('maps job types to Chinese in the execution list', async () => {
    installFetchMock();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    const list = await screen.findByTestId('execution-item-list');
    expect(list).toHaveTextContent('评论补采');
    expect(list).toHaveTextContent('执行中');
    expect(list).toHaveTextContent('补采任务');
    expect(list).toHaveTextContent('已超时');
  });

  it('shows run batch summary without engineering abbreviations', async () => {
    installFetchMock();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    const runs = await screen.findByTestId('run-batch-list');
    expect(runs).toHaveTextContent('推荐页巡检');
    expect(runs).toHaveTextContent(/0 个等待执行/);
    expect(runs).toHaveTextContent('手动触发');
    expect(screen.queryByText(/P\d+\s+R\d+/)).not.toBeInTheDocument();
  });

  it('hides JSON behind technical details until expanded', async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    await screen.findByTestId('execution-item-list');
    await user.click(await screen.findByRole('button', { name: /评论补采/ }));
    expect(screen.getByTestId('job-detail-panel')).toBeInTheDocument();
    const tech = screen.getByTestId('job-tech-details');
    expect(tech).not.toHaveAttribute('open');
    await user.click(screen.getByText('查看技术详情'));
    expect(tech).toHaveAttribute('open');
    expect(tech.textContent).toContain('payload');
  });

  it('shows confirm dialog with distinct dismiss and action labels', async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<OperationsPage role="supervisor" userId="supervisor-user" />);

    await user.click(await screen.findByRole('button', { name: '处理超时执行项' }));
    const dialog = await screen.findByTestId('confirm-dialog');
    expect(dialog).toHaveTextContent('将把 2 个超过超时阈值');
    expect(screen.getByRole('button', { name: '返回' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '确定处理' })).toBeInTheDocument();
  });
});
