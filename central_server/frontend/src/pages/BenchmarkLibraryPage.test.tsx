import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

  it('shows edit panel and pagination summary', async () => {
    installFetchMock();
    render(<BenchmarkLibraryPage role="supervisor" userId="supervisor-user" />);
    expect(await screen.findByText(/共 \d+ 条/)).toBeInTheDocument();
    expect(await screen.findByTestId('benchmark-edit-panel')).toBeInTheDocument();
  });

  it('shows empty state CTA when list is empty', async () => {
    installFetchMock();
    window.history.replaceState({}, '', '/reference-library?content_query=__no_match__');
    const onOpen = vi.fn();
    render(<BenchmarkLibraryPage role="supervisor" userId="supervisor-user" onOpenIntelligencePool={onOpen} />);
    const cta = await screen.findByTestId('benchmark-empty-cta');
    await userEvent.click(cta);
    expect(onOpen).toHaveBeenCalled();
  });

  it('shows collected comments in selected benchmark detail', async () => {
    installFetchMock();
    render(<BenchmarkLibraryPage role="supervisor" userId="supervisor-user" />);
    expect(await screen.findByText('评论内容')).toBeInTheDocument();
    expect(await screen.findByText('求推荐，怎么联系？')).toBeInTheDocument();
    expect(screen.getByText('评论者A')).toBeInTheDocument();
  });
});
