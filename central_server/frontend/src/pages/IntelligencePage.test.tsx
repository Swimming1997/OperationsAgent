import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { IntelligencePage } from './IntelligencePage';

describe('IntelligencePage', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/intelligence');
  });

  it('renders scenario tabs and simplified table', async () => {
    installFetchMock();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);

    expect(screen.getByText('列表加载中')).toBeInTheDocument();
    expect(await screen.findByTestId('intelligence-scenario-tabs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '待处理' })).toHaveClass('selected');
    expect(await screen.findAllByText('SCI论文投稿避坑')).not.toHaveLength(0);
    expect(screen.getByTestId('intelligence-table-head')).toHaveClass('intelligence-content-row');
    expect(await screen.findByText('这是一条详情正文')).toBeInTheDocument();
    expect(screen.getByText('发现位置')).toBeInTheDocument();
    expect(screen.getByText('推荐判断')).toBeInTheDocument();
    expect(screen.getByText('评论内容')).toBeInTheDocument();
    expect(screen.getByText('求推荐，怎么联系？')).toBeInTheDocument();
    expect(screen.getAllByText('内容候选').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /^入库$/ })).toBeInTheDocument();
  });

  it('prefills scenario preset fields when opening advanced filters', async () => {
    installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('SCI论文投稿避坑');

    await user.click(screen.getByRole('button', { name: '高级筛选' }));
    const advancedFilters = screen.getByTestId('intelligence-advanced-filters');

    expect(within(advancedFilters).getByLabelText('入库状态')).toHaveValue('false');
    expect(within(advancedFilters).getByLabelText('发现时间不早于')).not.toHaveValue('');
    expect(within(advancedFilters).getByLabelText('入库状态')).not.toBeDisabled();
  });

  it('saves advanced scenario filters for current tab', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('SCI论文投稿避坑');

    await user.click(screen.getByRole('button', { name: '高级筛选' }));
    await user.clear(within(screen.getByTestId('intelligence-advanced-filters')).getByLabelText('最低点赞'));
    await user.type(within(screen.getByTestId('intelligence-advanced-filters')).getByLabelText('最低点赞'), '88');
    await user.click(screen.getByRole('button', { name: '保存筛选' }));

    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.url.includes('/api/product/me/intelligence/scenario-filters/pending') &&
            request.init?.method === 'PUT',
        ),
      ).toBe(true),
    );
    expect(await screen.findByText('筛选已保存')).toBeInTheDocument();
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

  it('runs rule re-evaluate from more panel', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('这是一条详情正文');

    await user.click(screen.getByRole('button', { name: /更多操作/ }));
    await user.click(screen.getByTestId('reevaluate-current-btn'));
    expect(await screen.findByTestId('reevaluate-results')).toBeInTheDocument();
    expect(screen.getByText('已跳过（人工锁定）')).toBeInTheDocument();
    expect(requests.some((request) => request.url.includes('/api/reference-library/items/re-evaluate'))).toBe(true);
  });

  it('hides re-evaluate action for operator role', async () => {
    installFetchMock();
    render(<IntelligencePage role="operator" userId="operator-user" />);
    await screen.findByText('这是一条详情正文');
    await userEvent.setup().click(screen.getByRole('button', { name: /更多操作/ }));
    expect(screen.queryByTestId('reevaluate-current-btn')).not.toBeInTheDocument();
  });

  it('adds to content library from primary action', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('这是一条详情正文');

    await user.click(within(screen.getByTestId('intelligence-primary-actions')).getByRole('button', { name: /^入库$/ }));
    expect(screen.getByDisplayValue('内容库')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^确认入库$/ }));
    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.url.includes('reference-library-items') &&
            request.init?.method === 'POST',
        ),
      ).toBe(true),
    );
  });

  it('marks watch later from primary action', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('这是一条详情正文');

    await user.click(within(screen.getByTestId('intelligence-primary-actions')).getByRole('button', { name: /^稍后处理$/ }));
    await waitFor(() => expect(requests.some((request) => request.url.includes('/select'))).toBe(true));
    await waitFor(() =>
      expect(requests.some((request) => request.url.includes('/manual-tags') && request.init?.method === 'PATCH')).toBe(
        true,
      ),
    );
  });

  it('submits detail enrichment from more panel', async () => {
    const { requests } = installFetchMock();
    const user = userEvent.setup();

    render(<IntelligencePage role="supervisor" userId="supervisor-user" />);
    await screen.findByText('这是一条详情正文');

    await user.click(screen.getByRole('button', { name: /更多操作/ }));
    await user.click(screen.getByRole('button', { name: /^重采详情$/ }));

    expect(await screen.findByText(/详情补采已提交/)).toBeInTheDocument();
    expect(requests.some((request) => request.url.includes('/enqueue-detail-fetch') && request.init?.method === 'POST')).toBe(true);
  });
});
