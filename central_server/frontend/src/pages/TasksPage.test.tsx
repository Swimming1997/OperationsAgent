import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { taskDetail } from '../test/mockData';
import { TasksPage } from './TasksPage';

describe('TasksPage', () => {
  it('filters task list by type without resetting create form', async () => {
    installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    const typeFilter = screen.getByLabelText('任务模板类型');

    expect(await screen.findByText('推荐流巡检')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^新建模板$/ }));
    const form = within(screen.getByTestId('dynamic-task-form'));
    expect(form.getByDisplayValue('推荐页巡检')).toBeInTheDocument();

    await user.selectOptions(typeFilter, 'creator_monitor_task');
    expect(form.getByDisplayValue('推荐页巡检')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /推荐流巡检/ })).not.toBeInTheDocument();

    await user.selectOptions(typeFilter, 'all');
    expect(await screen.findByRole('button', { name: /推荐流巡检/ })).toBeInTheDocument();
  });

  it('opens new template form from sidebar button', async () => {
    installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('推荐流巡检');
    await user.click(screen.getByRole('button', { name: /推荐流巡检/ }));
    expect(await screen.findByText('编辑模板')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^新建模板$/ }));
    const panel = screen.getByTestId('dynamic-task-form').closest('aside')!;
    expect(within(panel).getByText('新建模板')).toBeInTheDocument();
    expect(within(screen.getByTestId('dynamic-task-form')).getByDisplayValue('推荐页巡检')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('模板类型'), 'creator_monitor_task');
    expect(await screen.findByTestId('benchmark-group-select')).toBeInTheDocument();
  });

  it('hydrates detail form when selecting an existing template', async () => {
    installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    const form = () => within(screen.getByTestId('dynamic-task-form'));
    await screen.findByText('推荐流巡检');
    expect(screen.getByText(/请选择任务模板/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /推荐流巡检/ }));

    await waitFor(() => {
      expect(screen.getByText('编辑模板')).toBeInTheDocument();
      expect(form().getByDisplayValue('推荐流巡检')).toBeInTheDocument();
      expect(form().getByDisplayValue('2')).toBeInTheDocument();
    });
  });

  it('falls back to config when typed_payload is empty', async () => {
    installFetchMock({
      taskDetail: {
        ...taskDetail,
        typed_payload: {},
        config: {
          feed_type: 'xhs_home_feed',
          target_count: 33,
          refresh_rounds: 4,
          per_round_scroll_target: 40,
        },
      },
    });
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await user.click(await screen.findByRole('button', { name: /推荐流巡检/ }));

    await waitFor(() => {
      const panel = within(screen.getByTestId('dynamic-task-form'));
      expect(panel.getByDisplayValue('33')).toBeInTheDocument();
      expect(panel.getByDisplayValue('4')).toBeInTheDocument();
    });
  });

  it('loads rule set and benchmark options for operator from business type bindings', async () => {
    installFetchMock({
      authRoles: ['operator'],
      authUserId: 'operator-user',
      authDisplayName: '运营甲',
    });
    const user = userEvent.setup();

    render(<TasksPage role="operator" userId="operator-user" />);
    await user.click(await screen.findByRole('button', { name: /推荐流巡检/ }));

    await waitFor(() => {
      const panel = within(screen.getByTestId('dynamic-task-form'));
      expect(panel.getByTestId('rule-set-select')).toHaveTextContent('SCI 关键词');
    });
  });

  it('runs selected task template with executor account', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await user.click(await screen.findByText('推荐流巡检'));
    await user.selectOptions(screen.getByTestId('executor-account-select'), 'account-1');
    await waitFor(() => expect(screen.getByRole('button', { name: /立即运行/ })).not.toBeDisabled());
    await user.click(screen.getByRole('button', { name: /立即运行/ }));

    await waitFor(() => expect(requests.some((request) => request.url.includes('/task-1/run'))).toBe(true));
    const runRequest = requests.find((request) => request.url.includes('/task-1/run') && request.init?.method === 'POST');
    const runBody = typeof runRequest?.init?.body === 'string' ? runRequest.init.body : '';
    expect(runBody).toContain('account-1');
    expect(await screen.findByText(/已创建 1 个 Job/)).toBeInTheDocument();
    expect(await screen.findByTestId('task-run-panel')).toHaveTextContent('任务执行成功，本次采样 10 条，新增 0 条');
  });

  it('renders run readiness blockers and disables manual run when agent is not ready', async () => {
    installFetchMock({ blockedReadiness: true });
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await user.click(await screen.findByText('推荐流巡检'));
    await user.selectOptions(screen.getByTestId('executor-account-select'), 'account-1');

    const cards = await screen.findAllByTestId('readiness-card');
    expect(cards.some((card) => card.textContent?.includes('当前不可运行'))).toBe(true);
    expect(screen.getByRole('button', { name: /立即运行/ })).toBeDisabled();
  });

  it('submits business type and rule set when saving', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<TasksPage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('推荐流巡检');
    await user.click(screen.getByRole('button', { name: /^新建模板$/ }));
    await user.selectOptions(screen.getByTestId('business-type-select'), 'type-1');
    await user.selectOptions(screen.getByTestId('rule-set-select'), 'rule-set-1');
    await user.click(screen.getByRole('button', { name: /保存/ }));

    await waitFor(() => expect(requests.some((request) => request.url.includes('/recommendation-feed'))).toBe(true));
    const saveRequest = requests.find((request) => request.url.includes('/recommendation-feed'));
    expect(saveRequest?.init?.body).toContain('type-1');
    expect(saveRequest?.init?.body).toContain('rule-set-1');
    expect(saveRequest?.init?.body).not.toContain('executor_account_id');
  });
});
