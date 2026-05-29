import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
import { BenchmarkLibraryPage } from './BenchmarkLibraryPage';

describe('BenchmarkLibraryPage', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/reference-library');
  });

  it('renders layered filters and benchmark table', async () => {
    installFetchMock();
    render(<BenchmarkLibraryPage role="supervisor" userId="supervisor-user" />);
    expect(screen.getAllByText('对标作品库').length).toBeGreaterThan(0);
    expect(screen.getByText('我的选中')).toBeInTheDocument();
    expect(screen.getByText('获客库')).toBeInTheDocument();
    expect(await screen.findByTestId('benchmark-library-table')).toBeInTheDocument();
  });

  it('shows disabled pending action hints', async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<BenchmarkLibraryPage role="supervisor" userId="supervisor-user" />);
    const table = await screen.findByTestId('benchmark-library-table');
    await user.click(within(table).getAllByRole('button')[0]);
    const rewrite = await screen.findByRole('button', { name: /仿写/ });
    expect(rewrite).toBeDisabled();
    expect(rewrite).toHaveAttribute('title', 'P1 仿写中心上线后开放');
  });

  it('shows collected comments in selected benchmark detail', async () => {
    installFetchMock();
    render(<BenchmarkLibraryPage role="supervisor" userId="supervisor-user" />);
    expect(await screen.findByText('评论内容')).toBeInTheDocument();
    expect(await screen.findByText('求推荐，怎么联系？')).toBeInTheDocument();
    expect(screen.getByText('评论者A')).toBeInTheDocument();
  });
});
