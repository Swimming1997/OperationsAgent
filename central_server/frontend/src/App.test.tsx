import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { setStoredToken } from './auth/storage';
import { installFetchMock } from './test/serverMock';

describe('App shell', () => {
  it('renders shell navigation after auth', async () => {
    installFetchMock();
    setStoredToken('test-token');
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('current-user-panel')).toHaveTextContent('演示主管');
    });
    expect(screen.getByRole('button', { name: /情报中心/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /任务模板/ }));
    expect(await screen.findByText('模板配置与手动执行')).toBeInTheDocument();
  });
});
