import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { installFetchMock } from '../test/serverMock';
import { BootstrapAdminPage } from './BootstrapAdminPage';

describe('BootstrapAdminPage', () => {
  it('renders bootstrap form fields', () => {
    installFetchMock();
    render(
      <AuthProvider>
        <BootstrapAdminPage />
      </AuthProvider>,
    );
    expect(screen.getByTestId('bootstrap-admin-page')).toBeInTheDocument();
    expect(screen.getByText('初始化管理员')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '创建并进入系统' })).toBeInTheDocument();
  });
});
