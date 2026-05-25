import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  bootstrapAdmin,
  clearAuth,
  fetchBootstrapStatus,
  fetchMe,
  login,
  logoutApi,
  persistLogin,
  type AuthUser,
} from '../api/auth';
import { isDevAuthEnabled, setDevAuthEnabled, setStoredToken } from './storage';
import type { Role } from '../types/api';
import { primaryRole } from '../utils/roleLabels';

export type AuthPhase = 'loading' | 'bootstrap' | 'login' | 'authenticated';

type AuthContextValue = {
  phase: AuthPhase;
  user: AuthUser | null;
  role: Role;
  userId: string;
  roles: string[];
  devAuth: boolean;
  setDevAuth: (enabled: boolean) => void;
  setDevIdentity: (role: Role, userId: string) => void;
  completeLogin: (user: AuthUser, token?: string) => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<AuthPhase>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);
  const [devAuth, setDevAuthState] = useState(isDevAuthEnabled());
  const [devRole, setDevRole] = useState<Role>('supervisor');
  const [devUserId, setDevUserId] = useState('supervisor-user');

  const completeLogin = useCallback((nextUser: AuthUser, token?: string) => {
    if (token) setStoredToken(token);
    setUser(nextUser);
    setPhase('authenticated');
  }, []);

  const refresh = useCallback(async () => {
    if (devAuth) {
      setPhase('authenticated');
      setUser(null);
      return;
    }
    try {
      const me = await fetchMe();
      setUser(me);
      setPhase('authenticated');
      return;
    } catch {
      clearAuth();
    }
    const status = await fetchBootstrapStatus();
    setPhase(status.needs_bootstrap ? 'bootstrap' : 'login');
    setUser(null);
  }, [devAuth]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      if (!devAuth) await logoutApi();
    } catch {
      // ignore
    }
    clearAuth();
    setUser(null);
    const status = await fetchBootstrapStatus();
    setPhase(status.needs_bootstrap ? 'bootstrap' : 'login');
  }, [devAuth]);

  const setDevAuth = useCallback((enabled: boolean) => {
    setDevAuthEnabled(enabled);
    setDevAuthState(enabled);
    if (enabled) {
      clearAuth();
      setUser(null);
      setPhase('authenticated');
    } else {
      void refresh();
    }
  }, [refresh]);

  const setDevIdentity = useCallback((role: Role, userId: string) => {
    setDevRole(role);
    setDevUserId(userId);
  }, []);

  const role = devAuth ? devRole : user ? primaryRole(user.roles) : 'operator';
  const userId = devAuth ? devUserId : user?.id || '';
  const roles = devAuth ? [devRole] : user?.roles || [];

  const value = useMemo<AuthContextValue>(
    () => ({
      phase,
      user,
      role,
      userId,
      roles,
      devAuth,
      setDevAuth,
      setDevIdentity,
      completeLogin,
      logout,
      refresh,
    }),
    [phase, user, role, userId, roles, devAuth, setDevAuth, setDevIdentity, completeLogin, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export async function performLogin(username: string, password: string) {
  const response = await login({ username, password });
  return persistLogin(response);
}

export async function performBootstrapAdmin(payload: {
  username: string;
  display_name: string;
  email?: string;
  password: string;
}) {
  const response = await bootstrapAdmin(payload);
  return persistLogin(response);
}
