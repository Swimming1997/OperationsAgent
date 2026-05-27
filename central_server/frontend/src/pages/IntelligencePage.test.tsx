import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { IntelligencePage } from './IntelligencePage';

describe('IntelligencePage', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/intelligence');
  });

  it('renders aligned table header and loads detail panel', async () => {
    installFetchMock();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);

    expect(screen.getByText('列表加载中')).toBeInTheDocument();
    expect(await screen.findAllByText('SCI论文投稿避坑')).not.toHaveLength(0);
    expect(screen.getByTestId('intelligence-table-head')).toHaveClass('content-row');
    expect(await screen.findByText('这是一条详情正文')).toBeInTheDocument();
    expect(screen.getAllByText('内容候选').length).toBeGreaterThan(0);
    expect(screen.getByText('采集来源')).toBeInTheDocument();
    expect(screen.getByText('关键词搜索')).toBeInTheDocument();
  });

  it('shows image fallback after cover load failure', async () => {
    installFetchMock();
    const { container } = render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('SCI论文投稿避坑');
    const image = container.querySelector('img');
    expect(image).toBeTruthy();
    fireEvent.error(image as HTMLImageElement);
    expect(await screen.findByText('无图')).toBeInTheDocument();
  });

  it('runs rule re-evaluate and shows skipped manual lock feedback', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('这是一条详情正文');

    await user.click(screen.getByTestId('reevaluate-current-btn'));
    expect(await screen.findByTestId('reevaluate-results')).toBeInTheDocument();
    expect(screen.getByText('已跳过（人工锁定）')).toBeInTheDocument();
    expect(screen.getByText('人工锁定，规则重评已跳过')).toBeInTheDocument();
    expect(requests.some((request) => request.url.includes('/api/reference-library/items/re-evaluate'))).toBe(true);
  });

  it('hides re-evaluate action for operator role', async () => {
    installFetchMock();
    render(<IntelligencePage role="operator" userId="operator-user" />);
    await screen.findByText('SCI论文投稿避坑');
    expect(screen.queryByRole('button', { name: /规则重评/ })).not.toBeInTheDocument();
  });

  it('sends select and note requests from detail actions', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('这是一条详情正文');

    await user.type(screen.getByPlaceholderText('添加处理备注'), '已处理');
    await user.click(screen.getByRole('button', { name: /选中/ }));
    await waitFor(() => expect(requests.some((request) => request.url.includes('/select'))).toBe(true));
  });
});
