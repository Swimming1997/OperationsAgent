import { LogIn, Plus, RefreshCw, Save } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getActiveAccountLogin, resetAccountLogin, startAccountLogin } from '../api/accountLogin';
import { fetchOptions } from '../api/options';
import { createAccount, createBusinessAccountType, getAccount, listAccounts, listAgents, listBusinessAccountTypes, listEmployees, updateAccount, updateBusinessAccountType } from '../api/resources';
import { useAuth } from '../auth/AuthContext';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { AccountLoginSession, BusinessAccountType, Employee, LocalAgent, PlatformAccount, ProductOptions, Role } from '../types/api';
import {
  formatAgentHeartbeat,
  formatAgentOptionLabel,
  isAgentLive,
  pickPreferredAgent,
  sortAgentsForDisplay,
  supportsAccountLogin,
} from '../utils/agentCapabilities';
import {
  authPillClassForAccount,
  isLoginSessionInProgress,
  isWaitingForAgent,
  labelAccountLoginBadge,
  labelAccountOperationalStatus,
  labelAuthStatus,
  labelLoginSessionStatus,
} from '../utils/authStatusLabels';

type Props = { role: Role; userId: string };

type RightPanelMode = 'idle' | 'create' | 'detail';

const FALLBACK_OPTIONS: ProductOptions = {
  roles: [],
  platforms: [{ value: 'xhs', label: 'xhs' }],
  feed_types: [],
  task_template_types: [],
  workflow_statuses: [],
  candidate_buckets: [],
  account_statuses: [
    { value: 'active', label: 'active' },
    { value: 'inactive', label: 'inactive' },
    { value: 'suspended', label: 'suspended' },
  ],
  agent_statuses: [{ value: 'online', label: 'online' }, { value: 'offline', label: 'offline' }],
};

function emptyCreateForm(defaults: { employeeId?: string; agentId?: string }): Partial<PlatformAccount> {
  return {
    platform: 'xhs',
    display_name: '',
    status: 'active',
    employee_id: defaults.employeeId,
    default_agent_id: defaults.agentId,
  };
}

export function AccountsPage({ role, userId }: Props) {
  const { user } = useAuth();
  const authEmployeeId = user?.employee_id ?? null;
  const [options, setOptions] = useState<ProductOptions>(FALLBACK_OPTIONS);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [types, setTypes] = useState<BusinessAccountType[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [agents, setAgents] = useState<LocalAgent[]>([]);
  const [selected, setSelected] = useState<PlatformAccount | null>(null);
  const [rightPanel, setRightPanel] = useState<RightPanelMode>('idle');
  const [accountForm, setAccountForm] = useState<Partial<PlatformAccount>>(() => emptyCreateForm({}));
  const [typeForm, setTypeForm] = useState<Partial<BusinessAccountType>>({ name: '', enabled: true });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loginSession, setLoginSession] = useState<AccountLoginSession | null>(null);
  const [loginMessage, setLoginMessage] = useState('');
  const [loginBusy, setLoginBusy] = useState(false);
  const readonly = false;

  const myEmployee = useMemo(
    () => employees.find((item) => item.user_id === userId) || (authEmployeeId ? { id: authEmployeeId, user_id: userId, display_name: user?.display_name || '', status: 'active' } as Employee : undefined),
    [employees, userId, authEmployeeId, user?.display_name],
  );

  const scopedEmployeeId = myEmployee?.id ?? authEmployeeId ?? null;

  const bindableAgents = useMemo(() => sortAgentsForDisplay(agents), [agents]);

  const liveLoginAgents = useMemo(
    () => bindableAgents.filter((item) => isAgentLive(item) && supportsAccountLogin(item.capabilities)),
    [bindableAgents],
  );

  const connectedAgent = useMemo(() => {
    const ownedLive = scopedEmployeeId
      ? liveLoginAgents.filter((item) => item.employee_id === scopedEmployeeId)
      : liveLoginAgents;
    return ownedLive[0] || liveLoginAgents[0];
  }, [liveLoginAgents, scopedEmployeeId]);

  const preferredAgent = useMemo(
    () => pickPreferredAgent(bindableAgents, scopedEmployeeId),
    [bindableAgents, scopedEmployeeId],
  );

  const employeeOptions = useMemo(() => employees.map((item) => ({ value: item.id, label: item.display_name, description: item.status })), [employees]);
  const agentOptions = useMemo(() => bindableAgents.map((item) => ({
    value: item.id,
    label: formatAgentOptionLabel(item),
    description: supportsAccountLogin(item.capabilities) ? '支持账号登录' : '未声明登录能力',
  })), [bindableAgents]);

  const platformOptions = options.platforms.length > 0 ? options.platforms : FALLBACK_OPTIONS.platforms;
  const canCreate = Boolean(accountForm.display_name?.trim());

  const operationalStatusOptions = [
    { value: 'active', label: '启用' },
    { value: 'inactive', label: '暂停' },
    { value: 'suspended', label: '已停用' },
  ];

  function patchAccountLoginState(account: PlatformAccount, session: AccountLoginSession | null): PlatformAccount {
    if (!session) {
      return { ...account, active_login_session_status: null };
    }
    if (session.status === 'logged_in') {
      return { ...account, auth_status: 'active', active_login_session_status: session.status };
    }
    return {
      ...account,
      auth_status: account.auth_status === 'active' ? 'active' : 'login_pending',
      active_login_session_status: session.status,
    };
  }

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const accountsPromise = listAccounts(role, userId);
      const agentsPromise = listAgents(role, userId);
      const optionsPromise = fetchOptions(role, userId).catch(() => FALLBACK_OPTIONS);
      const typesPromise = role === 'operator'
        ? Promise.resolve([] as BusinessAccountType[])
        : listBusinessAccountTypes(role, userId);
      const employeesPromise = role === 'operator'
        ? Promise.resolve([] as Employee[])
        : listEmployees(role, userId);

      const [nextOptions, nextAccounts, nextTypes, nextEmployees, nextAgents] = await Promise.all([
        optionsPromise,
        accountsPromise,
        typesPromise,
        employeesPromise,
        agentsPromise,
      ]);

      setOptions(nextOptions);
      setAccounts(nextAccounts);
      setTypes(nextTypes);
      setEmployees(nextEmployees);
      setAgents(nextAgents);

      setSelected((current) => {
        if (!current?.id) return current;
        return nextAccounts.find((item) => item.id === current.id) || null;
      });
      setRightPanel((mode) => {
        if (mode === 'create') return 'create';
        return mode;
      });
    } catch (err) {
      const apiErr = err as { status?: number };
      if (apiErr.status === 403) {
        setError('无权限访问当前资源');
      } else {
        setError(err instanceof Error ? err.message : '账号资源加载失败');
      }
    } finally {
      setLoading(false);
    }
  }, [role, userId]);

  useEffect(() => { void reload(); }, [reload]);

  useEffect(() => {
    if (!selected?.id) {
      setLoginSession(null);
      setLoginMessage('');
      return;
    }
    let cancelled = false;
    const accountId = selected.id;
    async function poll() {
      try {
        const active = await getActiveAccountLogin(role, accountId, userId);
        if (cancelled) return;
        const inProgress = active && ['created', 'waiting_agent', 'launching_browser', 'waiting_user_login', 'checking_auth'].includes(active.status);
        setLoginSession(active);
        if (active) {
          setAccounts((items) => items.map((item) => (item.id === accountId ? patchAccountLoginState(item, active) : item)));
          setSelected((item) => (item && item.id === accountId ? patchAccountLoginState(item, active) : item));
          if (active.status === 'logged_in') {
            setAccountForm((item) => (item && 'id' in item && item.id === accountId ? { ...item, auth_status: 'active' } : item));
            setLoginMessage('登录已完成，可在浏览器中确认后手动关闭 Chrome 窗口。');
          } else if (!inProgress) {
            setLoginMessage(labelLoginSessionStatus(active.status));
          }
        } else {
          setLoginSession(null);
          try {
            const fresh = await getAccount(role, accountId, userId);
            if (cancelled) return;
            setAccounts((items) => items.map((item) => (item.id === accountId ? fresh : item)));
            setSelected((item) => (item && item.id === accountId ? fresh : item));
            setAccountForm((item) => (item && 'id' in item && item.id === accountId ? { ...fresh } : item));
            if (fresh.auth_status === 'active') {
              setLoginMessage('登录已完成，可在浏览器中确认后手动关闭 Chrome 窗口。');
            }
          } catch {
            setAccounts((items) => items.map((item) => (item.id === accountId ? { ...item, active_login_session_status: null } : item)));
            setSelected((item) => (item && item.id === accountId ? { ...item, active_login_session_status: null } : item));
          }
        }
      } catch {
        if (!cancelled) setLoginSession(null);
      }
    }
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [role, userId, selected?.id]);

  function openCreate() {
    setSelected(null);
    setRightPanel('create');
    setLoginSession(null);
    setLoginMessage('');
    setAccountForm(emptyCreateForm({
      employeeId: myEmployee?.id ?? authEmployeeId ?? undefined,
      agentId: preferredAgent?.id,
    }));
  }

  function chooseAccount(account: PlatformAccount) {
    setSelected(account);
    setRightPanel('detail');
    setAccountForm({ ...account });
    setLoginSession(null);
    setLoginMessage('');
  }

  async function saveAccount() {
    if (!canCreate) return;
    setError('');
    try {
      const base = {
        platform: accountForm.platform || 'xhs',
        display_name: accountForm.display_name!.trim(),
        employee_id: accountForm.employee_id ?? myEmployee?.id ?? authEmployeeId ?? null,
        business_account_type_id: accountForm.business_account_type_id ?? null,
        default_agent_id: accountForm.default_agent_id || null,
      };
      const saved = selected?.id
        ? await updateAccount(role, selected.id, { ...base, status: accountForm.status || 'active' }, userId)
        : await createAccount(role, base, userId);
      await reload();
      setSelected(saved);
      setRightPanel('detail');
      setAccountForm({ ...saved });
    } catch (err) {
      setError(err instanceof Error ? err.message : '账号保存失败');
    }
  }

  async function saveType() {
    if (!typeForm.name?.trim()) return;
    setError('');
    try {
      if (typeForm.id) {
        await updateBusinessAccountType(role, typeForm.id, typeForm, userId);
      } else {
        await createBusinessAccountType(role, { name: typeForm.name.trim(), description: typeForm.description ?? null, enabled: typeForm.enabled ?? true }, userId);
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : '业务账号类型保存失败');
    }
  }

  async function refreshLoginStatus() {
    if (!selected?.id) return;
    setLoginBusy(true);
    setError('');
    try {
      const fresh = await getAccount(role, selected.id, userId);
      const active = await getActiveAccountLogin(role, selected.id, userId);
      setLoginSession(active);
      const patched = patchAccountLoginState(fresh, active);
      setSelected(patched);
      setAccounts((items) => items.map((item) => (item.id === selected.id ? patched : item)));
      setAccountForm({ ...patched });
      setLoginMessage(active ? labelLoginSessionStatus(active.status) : `当前登录态：${labelAuthStatus(patched.auth_status)}`);
    } catch (err) {
      setLoginMessage(err instanceof Error ? err.message : '刷新失败');
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleResetLogin() {
    if (!selected?.id) return;
    setLoginBusy(true);
    setLoginMessage('');
    setError('');
    try {
      const result = await resetAccountLogin(role, selected.id, userId);
      setLoginSession(null);
      const fresh = await getAccount(role, selected.id, userId);
      setSelected(fresh);
      setAccounts((items) => items.map((item) => (item.id === selected.id ? fresh : item)));
      setAccountForm({ ...fresh });
      setLoginMessage(result.message || '登录已取消，可重新发起登录');
    } catch (err) {
      setLoginMessage(err instanceof Error ? err.message : '取消登录失败');
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleStartLogin(force = false) {
    if (!selected?.id) return;
    setLoginBusy(true);
    setLoginMessage('');
    setError('');
    try {
      const result = await startAccountLogin(role, selected.id, userId, { force });
      setLoginSession(result.session);
      setLoginMessage(result.message);
      const patched = patchAccountLoginState(selected, result.session);
      setSelected(patched);
      setAccounts((items) => items.map((item) => (item.id === selected.id ? patched : item)));
    } catch (err) {
      setLoginMessage(err instanceof Error ? err.message : '发起登录失败');
    } finally {
      setLoginBusy(false);
    }
  }

  function renderAgentStatus() {
    if (connectedAgent) {
      return (
        <div className="agent-status-card agent-status-online">
          <b>本地 Agent 已连接</b>
          <span>设备：{connectedAgent.device_name || connectedAgent.id}</span>
          <span>归属：{connectedAgent.employee_display_name || '—'}</span>
          <span>最近心跳：{formatAgentHeartbeat(connectedAgent)}</span>
          <p className="login-hint">新建账号将默认绑定此 Agent；发起登录后可自动拉起浏览器。</p>
          {bindableAgents.length > 1 ? (
            <span className="login-hint">其它登记设备：{bindableAgents.filter((item) => item.id !== connectedAgent.id).map((item) => formatAgentOptionLabel(item)).join('；')}</span>
          ) : null}
        </div>
      );
    }
    return (
      <div className="agent-status-card agent-status-offline">
        <b>本地 Agent 未连接</b>
        <span>账号可以先创建；发起登录后会进入「等待 Agent 上线」，Agent 启动后将自动打开浏览器。</span>
        {bindableAgents.length > 0 ? (
          <span>已登记设备：{bindableAgents.map((item) => formatAgentOptionLabel(item)).join('；')}</span>
        ) : (
          <span>尚未登记本机 Agent。请在本机运行 Local Agent，并由管理员在「Agent 管理」中将该设备绑定到本员工。</span>
        )}
      </div>
    );
  }

  function renderRightPanel() {
    if (rightPanel === 'idle') {
      return (
        <div className="detail-empty-state">
          <EmptyState text="选择左侧账号查看详情，或点击「添加运营账号」开始接入" />
        </div>
      );
    }

    const isCreate = rightPanel === 'create';
    const sessionStatus = loginSession?.status ?? selected?.active_login_session_status ?? null;
    const waitingAgent = selected ? isWaitingForAgent(selected, sessionStatus) : false;
    const loginInProgress = isLoginSessionInProgress(sessionStatus);
    const loggedIn = selected?.auth_status === 'active';
    const canRelogin = loggedIn || selected?.auth_status === 'error';

    return (
      <>
        <div className="form-stack">
          <label>账号备注名</label>
          <input
            value={accountForm.display_name || ''}
            onChange={(event) => setAccountForm({ ...accountForm, display_name: event.target.value })}
            placeholder="如：XHS-账号A"
          />
          <label>平台</label>
          <select value={accountForm.platform || 'xhs'} onChange={(event) => setAccountForm({ ...accountForm, platform: event.target.value })}>
            {platformOptions.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
          {role !== 'operator' ? (
            <ResourceSelect label="绑定员工" value={accountForm.employee_id} options={employeeOptions} onChange={(value) => setAccountForm({ ...accountForm, employee_id: value })} />
          ) : null}
          <ResourceSelect
            label="绑定 Agent（可选）"
            value={accountForm.default_agent_id}
            options={agentOptions}
            onChange={(value) => setAccountForm({ ...accountForm, default_agent_id: value || undefined })}
            allowEmpty
          />
          {isCreate && !liveLoginAgents.length ? (
            <p className="login-hint">暂无在线 Agent，账号仍可先创建；发起登录后将等待 Agent 上线。</p>
          ) : null}
          {!isCreate && selected ? (
            <>
              <label>账号状态</label>
              <select value={accountForm.status || 'active'} onChange={(event) => setAccountForm({ ...accountForm, status: event.target.value })}>
                {operationalStatusOptions.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </>
          ) : null}
          {!isCreate && selected ? (
            <div className="detail-section">
              <b>登录信息</b>
              <span>登录态：{labelAccountLoginBadge({ ...selected, active_login_session_status: sessionStatus })}</span>
              <span>账号用途：{selected.account_role === 'operated_account' ? '运营号' : '情报采集号'}</span>
              <span>健康状态：{selected.health_status || 'healthy'}</span>
              <span>Local Agent：{selected.default_agent_device_name || '—'}</span>
              <span>Profile Key：{selected.profile_key || '—'}</span>
              <span>CDP 端口：{selected.login_cdp_port ?? '—'}</span>
              {selected.platform_nickname ? <span>平台昵称：{selected.platform_nickname}</span> : null}
            </div>
          ) : null}
          <button type="button" onClick={() => void saveAccount()} disabled={readonly || !canCreate}>
            <Save size={14} />
            {isCreate ? '创建账号' : '保存账号'}
          </button>
        </div>
        {!isCreate && selected ? (
          <div className="login-session-panel">
            <div className="panel-title">平台登录</div>
            <div className="login-session-card">
              <span className={`auth-pill ${authPillClassForAccount({ ...selected, active_login_session_status: sessionStatus })}`}>
                {labelAccountLoginBadge({ ...selected, active_login_session_status: sessionStatus })}
              </span>
              {loginSession ? <span>{labelLoginSessionStatus(loginSession.status)}</span> : null}
              {loginMessage ? <p className="login-hint">{loginMessage}</p> : null}
              {loginSession?.error_message && loginSession.status === 'waiting_user_login' && /验证|滑块|安全/.test(loginSession.error_message) ? (
                <p className="login-hint">{loginSession.error_message}</p>
              ) : null}
              {loginSession?.error_message && loginSession.status !== 'waiting_user_login' ? (
                <p className="inline-error">{loginSession.error_message}</p>
              ) : null}
              {loginSession?.status === 'waiting_agent' ? <p className="login-hint">等待本地 Agent 上线后将自动打开浏览器，请保持 Agent 运行。</p> : null}
              {loginSession?.status === 'waiting_user_login' ? (
                <p className="login-hint">请在 Agent 打开的 Chrome 窗口完成小红书登录（扫码/验证码）。登录成功前请勿关闭该窗口；Agent 会连续两次确认登录态后才标记完成。</p>
              ) : null}
            </div>
            <div className="detail-actions">
              {loginInProgress || waitingAgent ? (
                <button type="button" className="secondary" disabled={loginBusy} onClick={() => void handleResetLogin()}>
                  取消登录
                </button>
              ) : canRelogin ? (
                <>
                  <button type="button" disabled={loginBusy} onClick={() => void handleStartLogin(true)}>
                    <LogIn size={14} />
                    重新登录
                  </button>
                  <button type="button" className="secondary" disabled={loginBusy} onClick={() => void handleResetLogin()}>
                    重置为未登录
                  </button>
                </>
              ) : (
                <button type="button" disabled={loginBusy} onClick={() => void handleStartLogin(false)}>
                  <LogIn size={14} />
                  发起登录
                </button>
              )}
              <button type="button" className="secondary" disabled={loginBusy} onClick={() => void refreshLoginStatus()}>
                <RefreshCw size={14} />
                刷新状态
              </button>
            </div>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="page-grid resource-grid">
      <aside className="filter-panel">
        <div className="panel-title">账号筛选</div>
        <label>平台</label>
        <select disabled><option>全部</option>{platformOptions.map((item) => <option key={item.value}>{item.label}</option>)}</select>
        <button type="button" className="secondary" onClick={() => void reload()}><RefreshCw size={14} />刷新</button>
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>账号管理</h1>
            <p className="ops-intro">添加运营账号并由本地 Agent 拉起浏览器完成平台登录，无需手工填写平台 ID。</p>
            <span>{accounts.length} 个运营账号</span>
          </div>
          <button type="button" className={rightPanel === 'create' ? 'primary-btn' : undefined} onClick={openCreate}><Plus size={14} />添加运营账号</button>
        </div>
        {error ? <ErrorState text={error} /> : null}
        {loading ? <LoadingState text="账号加载中" /> : accounts.length === 0 ? (
          <EmptyState text="暂无运营账号，点击右上角「添加运营账号」" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head account-row account-row-v2">
              <span>备注名</span><span>平台</span><span>用途</span><span>健康</span><span>登录态</span><span>Agent</span><span>Profile</span>
            </div>
            {accounts.map((account) => (
              <button key={account.id} type="button" className={`table-row account-row account-row-v2 ${selected?.id === account.id ? 'selected' : ''}`} onClick={() => chooseAccount(account)}>
                <span className="strong">{account.display_name}</span>
                <span>{account.platform}</span>
                <span>{account.account_role === 'operated_account' ? '运营号' : '采集号'}</span>
                <span>{account.health_status || 'healthy'}</span>
                <span><span className={`auth-pill ${authPillClassForAccount(account)}`}>{labelAccountLoginBadge(account)}</span></span>
                <span>{account.default_agent_device_name || '—'}</span>
                <span>{account.profile_key || '—'}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      <aside className={`detail-panel ${rightPanel === 'create' ? 'detail-panel-create' : ''}`}>
        {renderAgentStatus()}
        <div className="panel-title">{rightPanel === 'create' ? '添加运营账号' : rightPanel === 'detail' ? '账号详情' : '账号详情'}</div>
        {renderRightPanel()}
        {role !== 'operator' ? (
          <div className="detail-section">
            <b>业务账号类型</b>
            <div className="mini-list">
              {types.map((item) => <button key={item.id} type="button" className="mini-row" onClick={() => setTypeForm(item)}>{item.name}<span>规则 {item.rule_set_count} / 对标组 {item.benchmark_group_count}</span></button>)}
            </div>
            <label>类型名称</label><input value={typeForm.name || ''} onChange={(event) => setTypeForm({ ...typeForm, name: event.target.value })} />
            <button type="button" onClick={() => void saveType()}><Save size={14} />保存类型</button>
          </div>
        ) : null}
      </aside>
    </section>
  );
}
