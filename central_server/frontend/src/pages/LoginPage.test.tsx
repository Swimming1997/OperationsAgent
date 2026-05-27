import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { setStoredToken } from '../auth/storage';
import { installFetchMock } from '../test/serverMock';
import { LoginPage } from './LoginPage';

describe('LoginPage', () => {
  it('renders login form and accepts credentials', async () => {
    installFetchMock();
    setStoredToken(null);
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    expect(screen.getByTestId('login-page')).toBeInTheDocument();
    await user.type(screen.getByLabelText('用户名'), 'supervisor');
    await user.type(screen.getByLabelText('密码'), 'secret');
    await user.click(screen.getByRole('button', { name: '登录' }));
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument();
  });

  it('allows switching to registration', async () => {
    installFetchMock();
    setStoredToken(null);
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );

    await user.click(screen.getByRole('tab', { name: '注册' }));
    await user.type(screen.getByLabelText('用户名'), 'operator2');
    await user.type(screen.getByLabelText('显示名'), '运营二号');
    await user.type(screen.getByLabelText('密码'), 'OperatorPass123!');
    await user.type(screen.getByLabelText('确认密码'), 'OperatorPass123!');
    await user.click(screen.getByRole('button', { name: '注册并进入系统' }));

    expect(screen.getByRole('button', { name: '注册并进入系统' })).toBeInTheDocument();
  });
});
