import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { installFetchMock } from '../test/serverMock';
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
});
