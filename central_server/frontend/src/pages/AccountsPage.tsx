import { LogIn, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getActiveAccountLogin, prepareBridgeChromeContext, resetAccountLogin, startAccountLogin, syncLocalBridgeLogin } from '../api/accountLogin';
import {
  discoverLocalBridgeAgents,
  fetchLocalBridgeSessionStatus,
  getLocalBridgeScanPorts,
  localBridgeHealthcheck,
  revalidateLocalBridgeSession,
  startLocalBridgeChrome,
} from '../api/localBridge';
import { fetchOptions } from '../api/options';
import { createAccount, createBusinessAccountType, deleteBusinessAccountType, getAccount, listAccounts, listAgents, listBusinessAccountTypes, listEmployees, registerMyLocalAgents, resolveDiscoveredLocalAgents, updateAccount, updateBusinessAccountType } from '../api/resources';
import { useAuth } from '../auth/AuthContext';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { AccountLoginSession, BusinessAccountType, Employee, LocalAgent, LocalBridgeDiscoveredAgent, LocalBridgeSessionStatus, PlatformAccount, ProductOptions, Role } from '../types/api';
import {
  formatAgentHeartbeat,
  formatAgentOptionLabel,
  isAgentLive,
  sortAgentsForDisplay,
  supportsAccountLogin,
} from '../utils/agentCapabilities';
import {
  authPillClassForAccount,
  isLoginSessionInProgress,
  isWaitingForAgent,
  labelAccountLoginBadge,
  labelAuthStatus,
  labelLoginSessionStatus,
  labelUsageStatus,
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
  const [typeEditorOpen, setTypeEditorOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loginSession, setLoginSession] = useState<AccountLoginSession | null>(null);
  const [loginMessage, setLoginMessage] = useState('');
  const [loginBusy, setLoginBusy] = useState(false);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [bridgeBusy, setBridgeBusy] = useState(false);
  const [bridgeError, setBridgeError] = useState('');
  const [bridgeSession, setBridgeSession] = useState<LocalBridgeSessionStatus | null>(null);
  const [adminEmployeeFilter, setAdminEmployeeFilter] = useState('');
  const [selectedLoginAgentId, setSelectedLoginAgentId] = useState('');
  const [registerPickerOpen, setRegisterPickerOpen] = useState(false);
  const [registerSelection, setRegisterSelection] = useState<string[]>([]);
  const [registerCandidates, setRegisterCandidates] = useState<Array<{ agentId: string; discovered: LocalBridgeDiscoveredAgent }>>([]);
  const [bridgeAlivePorts, setBridgeAlivePorts] = useState<number[]>([]);
  const [businessTypeFilter, setBusinessTypeFilter] = useState('');
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

  const ownedAgents = useMemo(
    () => (scopedEmployeeId ? bindableAgents.filter((item) => item.employee_id === scopedEmployeeId) : bindableAgents),
    [bindableAgents, scopedEmployeeId],
  );

  const connectedAgent = useMemo(() => {
    const ownedLive = scopedEmployeeId
      ? liveLoginAgents.filter((item) => item.employee_id === scopedEmployeeId)
      : liveLoginAgents;
    return ownedLive[0] || liveLoginAgents[0];
  }, [liveLoginAgents, scopedEmployeeId]);

  const loginAgentPickerOptions = useMemo(
    () => ownedAgents.map((item) => ({
      id: item.id,
      label: formatAgentOptionLabel(item),
      online: isAgentLive(item),
    })),
    [ownedAgents],
  );

  const employeeOptions = useMemo(() => employees.map((item) => ({ value: item.id, label: item.display_name, description: item.status })), [employees]);
  const businessTypeOptions = useMemo(
    () => types.map((item) => ({ value: item.id, label: item.name, description: item.description || undefined })),
    [types],
  );
  const businessTypeFilterOptions = useMemo(
    () => [{ value: '', label: '全部业务类型', description: '显示全部' }, ...businessTypeOptions],
    [businessTypeOptions],
  );
  const managementEmployeeOptions = useMemo(
    () => [{ value: '', label: '全部运营账号', description: '显示全部' }, ...employeeOptions],
    [employeeOptions],
  );
  const platformOptions = options.platforms.length > 0 ? options.platforms : FALLBACK_OPTIONS.platforms;
  const canCreate = Boolean(accountForm.display_name?.trim() && accountForm.business_account_type_id);
  const visibleAccounts = useMemo(
    () => accounts.filter((item) => {
      if (adminEmployeeFilter && item.employee_id !== adminEmployeeFilter) return false;
      if (businessTypeFilter && item.business_account_type_id !== businessTypeFilter) return false;
      return true;
    }),
    [accounts, adminEmployeeFilter, businessTypeFilter],
  );

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
    return { ...account, auth_status: 'active', active_login_session_status: session.status, usage_status: 'ready' };
    }
    return {
      ...account,
      auth_status: account.auth_status === 'active' ? 'active' : 'login_pending',
      active_login_session_status: session.status,
    usage_status: session.status === 'waiting_user_login' ? 'need_verify' : 'need_login',
    };
  }

  const reload = useCallback(async (): Promise<LocalAgent[]> => {
    setLoading(true);
    setError('');
    try {
      const accountsPromise = listAccounts(role, userId);
      const agentsPromise = listAgents(role, userId);
      const optionsPromise = fetchOptions(role, userId).catch(() => FALLBACK_OPTIONS);
      const typesPromise = listBusinessAccountTypes(role, userId);
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
      return nextAgents;
    } catch (err) {
      const apiErr = err as { status?: number };
      if (apiErr.status === 403) {
        setError('无权限访问当前资源');
      } else {
        setError(err instanceof Error ? err.message : '账号资源加载失败');
      }
      return [];
    } finally {
      setLoading(false);
    }
  }, [role, userId]);

  useEffect(() => { void reload(); }, [reload]);

  useEffect(() => {
    let cancelled = false;
    async function checkBridge() {
      try {
        const result = await localBridgeHealthcheck();
        if (cancelled) return;
        setBridgeReady(result.status === 'ok');
        setBridgeAlivePorts(result.ports);
        if (result.status === 'ok') setBridgeError('');
      } catch (err) {
        if (cancelled) return;
        setBridgeReady(false);
        setBridgeError(err instanceof Error ? err.message : '本机助手不可达');
      }
    }
    void checkBridge();
    const timer = window.setInterval(() => { void checkBridge(); }, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selected?.id) {
      setBridgeSession(null);
      setLoginSession(null);
      setLoginMessage('');
      return;
    }
    let cancelled = false;
    const accountId = selected.id;
    async function poll() {
      try {
        const [active, localSession] = await Promise.all([
          getActiveAccountLogin(role, accountId, userId),
          fetchLocalBridgeSessionStatus(accountId, {
            ports: bridgeAlivePorts.length ? bridgeAlivePorts : undefined,
            cdp_port: selected?.login_cdp_port ?? null,
          }).catch(() => null),
        ]);
        if (cancelled) return;
        const inProgress = active && ['created', 'waiting_agent', 'launching_browser', 'waiting_user_login', 'checking_auth'].includes(active.status);
        setLoginSession(active);
        setBridgeSession(localSession);
        if (active) {
          setAccounts((items) => items.map((item) => (item.id === accountId ? patchAccountLoginState(item, active) : item)));
          setSelected((item) => (item && item.id === accountId ? patchAccountLoginState(item, active) : item));
          if (active.status === 'logged_in' && localSession?.status === 'ready') {
            setAccountForm((item) => (item && 'id' in item && item.id === accountId ? { ...item, auth_status: 'active' } : item));
            setLoginMessage('登录已完成，可在浏览器中确认后手动关闭 Chrome 窗口。');
          } else if (active.status === 'logged_in' && localSession?.status && localSession.status !== 'ready') {
            setLoginMessage(localSession.message || '中央显示已登录，但本机会话尚未就绪，请先完成浏览器登录后再校验。');
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
            if (fresh.auth_status === 'active' && localSession?.status === 'ready') {
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
  }, [role, userId, selected?.id, selected?.login_cdp_port, bridgeAlivePorts]);

  function openCreate() {
    setSelected(null);
    setRightPanel('create');
    setLoginSession(null);
    setBridgeSession(null);
    setLoginMessage('');
    setAccountForm(emptyCreateForm({
      employeeId: myEmployee?.id ?? authEmployeeId ?? undefined,
    }));
  }

  function chooseAccount(account: PlatformAccount) {
    setSelected(account);
    setRightPanel('detail');
    setAccountForm({ ...account });
    setLoginSession(null);
    setLoginMessage('');
    setBridgeSession(null);
    setSelectedLoginAgentId('');
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

  function openNewType() {
    setTypeForm({ name: '', enabled: true });
    setTypeEditorOpen(true);
  }

  function openEditType(item: BusinessAccountType) {
    setTypeForm(item);
    setTypeEditorOpen(true);
  }

  function closeTypeEditor() {
    setTypeEditorOpen(false);
    setTypeForm({ name: '', enabled: true });
  }

  async function saveType() {
    if (!typeForm.name?.trim()) return;
    setError('');
    try {
      if (typeForm.id) {
        await updateBusinessAccountType(role, typeForm.id, { name: typeForm.name.trim(), description: typeForm.description ?? null }, userId);
      } else {
        await createBusinessAccountType(role, { name: typeForm.name.trim(), description: typeForm.description ?? null, enabled: true }, userId);
      }
      await reload();
      closeTypeEditor();
    } catch (err) {
      setError(err instanceof Error ? err.message : '业务账号类型保存失败');
    }
  }

  async function removeType(type: BusinessAccountType) {
    setError('');
    try {
      await deleteBusinessAccountType(role, type.id, userId);
      if (typeForm.id === type.id) {
        closeTypeEditor();
      }
      if (businessTypeFilter === type.id) {
        setBusinessTypeFilter('');
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : '业务账号类型删除失败');
    }
  }

  async function refreshLoginStatus() {
    if (!selected?.id) return;
    setLoginBusy(true);
    setError('');
    try {
      const [fresh, active, localSession] = await Promise.all([
        getAccount(role, selected.id, userId),
        getActiveAccountLogin(role, selected.id, userId),
        fetchLocalBridgeSessionStatus(selected.id, {
          ports: bridgeAlivePorts.length ? bridgeAlivePorts : undefined,
          cdp_port: selected.login_cdp_port,
        }).catch(() => null),
      ]);
      setLoginSession(active);
      setBridgeSession(localSession);
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

  async function handleBridgeStart() {
    if (!selected?.id) return;
    const ports = bridgeAlivePorts.length ? bridgeAlivePorts : getLocalBridgeScanPorts();
    if (!bridgeAlivePorts.length) {
      setBridgeError(`本机助手未连接。请先启动 local_agent（bridge 端口 ${ports.join(', ')}）`);
      return;
    }
    setBridgeBusy(true);
    setLoginBusy(true);
    setBridgeError('');
    setLoginMessage('正在准备 CDP 端口并拉起 Chrome…');
    try {
      const ctx = await prepareBridgeChromeContext(role, selected.id, userId);
      const start = await startLocalBridgeChrome(
        {
          account_id: selected.id,
          profile_key: ctx.profile_key,
          port: ctx.login_cdp_port,
        },
        { ports },
      );
      const session = await fetchLocalBridgeSessionStatus(selected.id, { ports, cdp_port: ctx.login_cdp_port });
      setBridgeSession(session);
      const patched = { ...selected, profile_key: ctx.profile_key, login_cdp_port: ctx.login_cdp_port };
      setSelected(patched);
      setAccountForm({ ...patched });
      setAccounts((items) => items.map((item) => (item.id === selected.id ? patched : item)));
      setLoginMessage(`浏览器已拉起（${start.cdp_url}），请在新窗口完成登录后点击「校验会话」。`);
    } catch (err) {
      const message = err instanceof Error ? err.message : '拉起浏览器失败';
      setBridgeError(message);
      setLoginMessage(message);
    } finally {
      setBridgeBusy(false);
      setLoginBusy(false);
    }
  }

  async function handleBridgeRevalidate() {
    if (!selected?.id) return;
    const ports = bridgeAlivePorts.length ? bridgeAlivePorts : getLocalBridgeScanPorts();
    if (!bridgeAlivePorts.length) {
      setBridgeError(`本机助手未连接。请先启动 local_agent（bridge 端口 ${ports.join(', ')}）`);
      return;
    }
    setBridgeBusy(true);
    setLoginBusy(true);
    setBridgeError('');
    setLoginMessage('正在校验本机会话…');
    try {
      let cdpPort = selected.login_cdp_port;
      if (!cdpPort) {
        const ctx = await prepareBridgeChromeContext(role, selected.id, userId);
        cdpPort = ctx.login_cdp_port;
        const patched = { ...selected, profile_key: ctx.profile_key, login_cdp_port: ctx.login_cdp_port };
        setSelected(patched);
        setAccountForm({ ...patched });
      }
      const session = await revalidateLocalBridgeSession(selected.id, { ports, cdp_port: cdpPort });
      setBridgeSession(session);
      if (session.status === 'ready') {
        if (session.message && session.message !== 'xhs session ready') {
          setLoginMessage(
            `检测到疑似会话可用（${session.message}），但为避免误判，暂不自动同步中央登录态。请在浏览器确认已进入个人主页后再重试校验。`,
          );
          return;
        }
        const sync = await syncLocalBridgeLogin(role, selected.id, {
          preferred_agent_id: selectedLoginAgentId || null,
          login_cdp_port: cdpPort,
          platform_nickname: session.platform_nickname,
          platform_home_url: session.platform_home_url,
          bridge_status: session.status,
        }, userId);
        const fresh = await getAccount(role, selected.id, userId);
        const patched = { ...fresh, auth_status: sync.auth_status };
        setSelected(patched);
        setAccountForm({ ...patched });
        setAccounts((items) => items.map((item) => (item.id === selected.id ? patched : item)));
        setLoginSession(null);
        setLoginMessage(sync.message || `本机会话已同步（CDP :${cdpPort}），中央登录态已更新。`);
      } else if (session.status === 'manual_verify_required') {
        const sync = await syncLocalBridgeLogin(role, selected.id, {
          preferred_agent_id: selectedLoginAgentId || null,
          login_cdp_port: cdpPort,
          platform_nickname: session.platform_nickname,
          platform_home_url: session.platform_home_url,
          bridge_status: session.status,
        }, userId);
        const fresh = await getAccount(role, selected.id, userId);
        setSelected(fresh);
        setAccountForm({ ...fresh });
        setAccounts((items) => items.map((item) => (item.id === selected.id ? fresh : item)));
        setLoginMessage(sync.message || '当前会话需要人工验证，请在浏览器中完成验证码后重试。');
      } else {
        // 保守降级：只有明确“跳转登录页”才自动把中央状态回落，避免一次误判把已登录打回未登录。
        if (session.status === 'expired' && session.message !== 'xhs redirected to login page') {
          setLoginMessage(
            `本地校验提示需登录（${session.message || 'xhs login is required'}），但未检测到明确跳转登录页，暂不自动回落中央状态。请在浏览器确认后再点一次校验。`,
          );
          return;
        }
        const sync = await syncLocalBridgeLogin(role, selected.id, {
          preferred_agent_id: selectedLoginAgentId || null,
          login_cdp_port: cdpPort,
          bridge_status: session.status,
        }, userId);
        const fresh = await getAccount(role, selected.id, userId);
        setSelected(fresh);
        setAccountForm({ ...fresh });
        setAccounts((items) => items.map((item) => (item.id === selected.id ? fresh : item)));
        setLoginMessage(sync.message || session.message || '会话暂不可用，请重新登录。');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '会话校验失败';
      setBridgeError(message);
      setLoginMessage(message);
    } finally {
      setBridgeBusy(false);
      setLoginBusy(false);
    }
  }

  async function submitRegisterAgents(agentIds: string[], force: boolean) {
    await registerMyLocalAgents(role, { agent_ids: agentIds, force }, userId);
    await reload();
    setRegisterPickerOpen(false);
    setRegisterSelection([]);
    setLoginMessage(`已将 ${agentIds.length} 台设备登记到当前运营账号`);
  }

  async function handleRegisterLocalAgent() {
    if (!scopedEmployeeId) {
      setBridgeError('当前登录账号未关联运营员工，无法登记设备');
      return;
    }
    setBridgeBusy(true);
    setBridgeError('');
    setLoginMessage('');
    try {
      const scan = await discoverLocalBridgeAgents();
      setBridgeAlivePorts(scan.alive_ports);
      const localItems = scan.items;
      if (!scan.alive_ports.length) {
        const portsHint = getLocalBridgeScanPorts().join(', ');
        setBridgeError(`未扫描到本机 bridge（端口 ${portsHint}）。请确认 local_agent 已用脚本启动。`);
        return;
      }
      if (!localItems.length) {
        setBridgeError(`已发现 ${scan.alive_ports.length} 个 bridge 端口，但 discover 无数据，请刷新后重试`);
        return;
      }
      const resolved = await resolveDiscoveredLocalAgents(
        role,
        {
          items: localItems.map((item) => ({
            agent_id: item.agent_id,
            device_name: item.device_name,
            machine_fingerprint: item.machine_fingerprint,
            bridge_port: item.bridge_port,
          })),
        },
        userId,
      );
      const candidates = resolved.map((row) => ({
        agentId: row.agent.id,
        discovered: localItems.find(
          (item) => item.agent_id === row.agent.id
            || (item.machine_fingerprint && item.machine_fingerprint === row.agent.machine_fingerprint)
            || item.device_name === row.agent.device_name,
        ) || {
          device_name: row.agent.device_name || '',
          machine_fingerprint: row.agent.machine_fingerprint || '',
          agent_id: row.agent.id,
          bridge_port: row.bridge_port ?? scan.alive_ports[0] ?? 18765,
          status: row.agent.status,
        },
      }));
      if (!candidates.length) {
        const hint = localItems
          .map((item) => `${item.device_name || '?'}${item.machine_fingerprint ? ` (${item.machine_fingerprint.slice(0, 12)}…)` : ''}`)
          .join('；');
        setBridgeError(
          `本机已发现 Agent（${hint}），但中央库中尚无对应设备记录。请查看 local_agent 窗口是否已 Registered；若已注册仍失败，请核对配置 center_url 是否与浏览器访问的中央地址一致（如 http://127.0.0.1:8000）。`,
        );
        return;
      }
      setRegisterCandidates(candidates);
      const matchIds = candidates.map((item) => item.agentId);
      if (matchIds.length > 1) {
        setRegisterSelection(matchIds);
        setRegisterPickerOpen(true);
        setLoginMessage(`扫描到 ${scan.alive_ports.length} 个 bridge 端口，${candidates.length} 台设备可登记，请勾选后确认`);
        return;
      }
      try {
        await submitRegisterAgents(matchIds, false);
      } catch (err) {
        const message = err instanceof Error ? err.message : '登记失败';
        if (message.includes('agent_bound_conflict')) {
          const confirmed = window.confirm('该设备已绑定其他运营，是否确认抢占并转绑到当前运营？');
          if (!confirmed) return;
          await submitRegisterAgents(matchIds, true);
        } else {
          throw err;
        }
      }
    } catch (err) {
      setBridgeError(err instanceof Error ? err.message : '登记本地 Agent 失败');
    } finally {
      setBridgeBusy(false);
    }
  }

  async function handleConfirmRegisterSelection() {
    if (!registerSelection.length) {
      setBridgeError('请至少选择一台设备');
      return;
    }
    setBridgeBusy(true);
    setBridgeError('');
    try {
      try {
        await submitRegisterAgents(registerSelection, false);
      } catch (err) {
        const message = err instanceof Error ? err.message : '登记失败';
        if (message.includes('agent_bound_conflict')) {
          const confirmed = window.confirm('所选设备中有已绑定其他运营的，是否全部抢占并转绑到当前运营？');
          if (!confirmed) return;
          await submitRegisterAgents(registerSelection, true);
        } else {
          throw err;
        }
      }
    } catch (err) {
      setBridgeError(err instanceof Error ? err.message : '登记失败');
    } finally {
      setBridgeBusy(false);
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
      const result = await startAccountLogin(role, selected.id, userId, {
        force,
        preferred_agent_id: selectedLoginAgentId || null,
      });
      setLoginSession(result.session);
      setLoginMessage(
        force
          ? `${result.message} 将打开新的登录浏览器（已清空本账号旧 Cookie、分配新调试端口），请在新窗口完成登录，勿使用之前打开的窗口。`
          : result.message,
      );
      const patched = patchAccountLoginState(selected, result.session);
      setSelected(patched);
      setAccounts((items) => items.map((item) => (item.id === selected.id ? patched : item)));
    } catch (err) {
      setLoginMessage(err instanceof Error ? err.message : '发起登录失败');
    } finally {
      setLoginBusy(false);
    }
  }

  function renderRegisterPicker() {
    if (!registerPickerOpen) return null;
    return (
      <div className="detail-section">
        <b>选择要登记的设备</b>
        <p className="login-hint">
          已扫描端口：{bridgeAlivePorts.length ? bridgeAlivePorts.join(', ') : getLocalBridgeScanPorts().join(', ')}
          （可通过环境变量 VITE_LOCAL_BRIDGE_PORTS 配置）
        </p>
        {registerCandidates.map(({ agentId, discovered }) => {
          const agent = agents.find((item) => item.id === agentId);
          if (!agent) return null;
          return (
            <label key={`${agentId}-${discovered.bridge_port}`} className="checkbox-row">
              <input
                type="checkbox"
                checked={registerSelection.includes(agentId)}
                onChange={(event) => {
                  if (event.target.checked) {
                    setRegisterSelection((prev) => (prev.includes(agentId) ? prev : [...prev, agentId]));
                  } else {
                    setRegisterSelection((prev) => prev.filter((id) => id !== agentId));
                  }
                }}
              />
              <span>
                {formatAgentOptionLabel(agent)}
                <span className="login-hint"> · bridge :{discovered.bridge_port}</span>
              </span>
            </label>
          );
        })}
        <div className="detail-actions">
          <button type="button" disabled={bridgeBusy} onClick={() => void handleConfirmRegisterSelection()}>
            确认登记
          </button>
          <button type="button" className="secondary" disabled={bridgeBusy} onClick={() => setRegisterPickerOpen(false)}>
            取消
          </button>
        </div>
      </div>
    );
  }

  function renderAgentStatus() {
    const canRegister = role === 'operator' && Boolean(scopedEmployeeId);

    if (connectedAgent) {
      return (
        <div className="agent-status-card agent-status-online">
          <b>本地 Agent 已连接</b>
          <span>设备：{connectedAgent.device_name || connectedAgent.id}</span>
          <span>归属：{connectedAgent.employee_display_name || '—'}</span>
          <span>最近心跳：{formatAgentHeartbeat(connectedAgent)}</span>
          <p className="login-hint">设备登记在运营账号下；小红书账号任务会按空闲设备自动调度。</p>
          <span>本机助手：{bridgeReady ? `已连接（${bridgeAlivePorts.length || 1} 个端口）` : '未连接'}</span>
          {bridgeAlivePorts.length ? (
            <span className="login-hint">bridge 端口：{bridgeAlivePorts.join(', ')}</span>
          ) : null}
          {ownedAgents.length > 1 ? (
            <span className="login-hint">运营设备池：{ownedAgents.map((item) => formatAgentOptionLabel(item)).join('；')}</span>
          ) : null}
          {canRegister ? (
            <div className="detail-actions">
              <button type="button" className="secondary" disabled={bridgeBusy || !bridgeReady} onClick={() => void handleRegisterLocalAgent()}>
                登记本地 Agent
              </button>
            </div>
          ) : null}
          {bridgeError ? <p className="inline-error">{bridgeError}</p> : null}
          {loginMessage && !selected ? <p className="login-hint">{loginMessage}</p> : null}
          {renderRegisterPicker()}
        </div>
      );
    }
    return (
      <div className="agent-status-card agent-status-offline">
        <b>本地 Agent 未连接</b>
        <span>请先在本机运行 Local Agent；登记到运营账号后，其下小红书账号任务将按空闲设备调度。</span>
        <span>本机助手：{bridgeReady ? `已连接（${bridgeAlivePorts.length || 1} 个端口）` : '未连接'}</span>
        {bridgeAlivePorts.length ? (
          <span className="login-hint">bridge 端口：{bridgeAlivePorts.join(', ')}</span>
        ) : null}
        {ownedAgents.length > 0 ? (
          <span>已登记设备：{ownedAgents.map((item) => formatAgentOptionLabel(item)).join('；')}</span>
        ) : (
          <span>尚未登记本机设备到当前运营账号。</span>
        )}
        {canRegister ? (
          <div className="detail-actions">
            <button type="button" className="secondary" disabled={bridgeBusy || !bridgeReady} onClick={() => void handleRegisterLocalAgent()}>
              登记本地 Agent
            </button>
          </div>
        ) : null}
        {bridgeError ? <p className="inline-error">{bridgeError}</p> : null}
        {loginMessage && !selected ? <p className="login-hint">{loginMessage}</p> : null}
        {renderRegisterPicker()}
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
            label="业务账号类型"
            value={accountForm.business_account_type_id}
            options={businessTypeOptions}
            onChange={(value) => setAccountForm({ ...accountForm, business_account_type_id: value })}
            allowEmpty
          />
          {businessTypeOptions.length === 0 ? (
            <p className="inline-error">请先由管理员在左侧添加业务账号类型，再创建账号。</p>
          ) : null}
          {isCreate && !liveLoginAgents.length ? (
            <p className="login-hint">暂无在线 Agent，账号仍可先创建；请先在上方「登记本地 Agent」将设备挂到运营账号。</p>
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
              <span>使用状态：{labelUsageStatus(selected.usage_status)}</span>
              <span>账号用途：{selected.account_role === 'operated_account' ? '运营号' : '情报采集号'}</span>
              <span>健康状态：{selected.health_status || 'healthy'}</span>
              <span>运营设备数：{scopedEmployeeId ? bindableAgents.filter((item) => item.employee_id === scopedEmployeeId).length : bindableAgents.length}</span>
              <span>Profile Key：{selected.profile_key || '—'}</span>
              <span>CDP 端口：{selected.login_cdp_port ?? '—'}</span>
              {selected.platform_nickname ? <span>平台昵称：{selected.platform_nickname}</span> : null}
              {bridgeSession ? <span>本机会话：{labelUsageStatus(bridgeSession.status === 'ready' ? 'ready' : bridgeSession.status === 'manual_verify_required' ? 'need_verify' : bridgeSession.status === 'expired' ? 'need_login' : 'unavailable')}</span> : null}
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
            <label>登录执行设备</label>
            <select
              value={selectedLoginAgentId}
              onChange={(event) => setSelectedLoginAgentId(event.target.value)}
              disabled={loginInProgress || waitingAgent}
            >
              <option value="">自动选择（在线且支持登录的设备中择优）</option>
              {loginAgentPickerOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}{item.online ? '' : '（离线）'}
                </option>
              ))}
            </select>
            <div className="login-session-card">
              <span className={`auth-pill ${authPillClassForAccount({ ...selected, active_login_session_status: sessionStatus })}`}>
                {labelAccountLoginBadge({ ...selected, active_login_session_status: sessionStatus })}
              </span>
              {loginSession ? <span>{labelLoginSessionStatus(loginSession.status)}</span> : null}
              {loginMessage ? <p className="login-hint">{loginMessage}</p> : null}
              {bridgeError ? <p className="inline-error">{bridgeError}</p> : null}
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
            {!bridgeReady && !bridgeAlivePorts.length ? (
              <p className="login-hint">本机助手未连接，无法直接拉起浏览器。请先运行 local_agent；或使用下方「发起登录」由 Agent 自动打开。</p>
            ) : null}
            <div className="detail-actions">
              <button type="button" className="secondary" disabled={bridgeBusy || loginBusy} onClick={() => void handleBridgeStart()}>
                启动登录浏览器
              </button>
              <button type="button" className="secondary" disabled={bridgeBusy || loginBusy || !bridgeAlivePorts.length} onClick={() => void handleBridgeRevalidate()}>
                校验会话
              </button>
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
        {role !== 'operator' ? (
          <ResourceSelect
            label="运营员工"
            value={adminEmployeeFilter}
            options={managementEmployeeOptions}
            onChange={(value) => setAdminEmployeeFilter(value || '')}
            allowEmpty={false}
          />
        ) : null}
        {role !== 'operator' ? (
          <div className="filter-group business-type-group">
            <div className="filter-group-title">业务账号类型</div>
            <ResourceSelect
              label="筛选账号"
              value={businessTypeFilter}
              options={businessTypeFilterOptions}
              onChange={(value) => setBusinessTypeFilter(value || '')}
              allowEmpty={false}
            />
            <div className="filter-group-body">
              <span className="filter-group-subtitle">已定义类型</span>
              <div className="mini-list scroll-list">
                {types.length === 0 ? <span className="muted-hint">暂无类型，请先添加</span> : types.map((item) => (
                  <div key={item.id} className={`mini-row ${typeEditorOpen && typeForm.id === item.id ? 'selected' : ''}`}>
                    <button type="button" className="mini-row-main" onClick={() => openEditType(item)}>
                      <span>{item.name}</span>
                      <small>{item.description || '无描述'}</small>
                    </button>
                    <button type="button" className="icon-button danger" title="删除业务账号类型" onClick={() => void removeType(item)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
              {!typeEditorOpen ? (
                <button type="button" className="secondary" onClick={openNewType}><Plus size={14} />新增类型</button>
              ) : (
                <div className="type-edit-form">
                  <span className="filter-group-subtitle">{typeForm.id ? '编辑类型' : '新增类型'}</span>
                  <label>类型名称</label><input value={typeForm.name || ''} onChange={(event) => setTypeForm({ ...typeForm, name: event.target.value })} />
                  <label>描述</label><input value={typeForm.description || ''} onChange={(event) => setTypeForm({ ...typeForm, description: event.target.value })} />
                  <div className="type-edit-actions">
                    <button type="button" onClick={() => void saveType()}><Save size={14} />保存类型</button>
                    <button type="button" className="secondary" onClick={closeTypeEditor}>取消</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <ResourceSelect
            label="业务账号类型"
            value={businessTypeFilter}
            options={businessTypeFilterOptions}
            onChange={(value) => setBusinessTypeFilter(value || '')}
            allowEmpty={false}
          />
        )}
        <div className="accounts-create-action">
          <button type="button" className={rightPanel === 'create' ? 'primary-btn' : undefined} onClick={openCreate}><Plus size={14} />添加运营账号</button>
        </div>
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>账号管理</h1>
            <p className="ops-intro">添加运营账号并由本地 Agent 拉起浏览器完成平台登录，无需手工填写平台 ID。</p>
            <span>{visibleAccounts.length} 个运营账号</span>
          </div>
          <button type="button" className="secondary" onClick={() => void reload()}><RefreshCw size={14} />刷新</button>
        </div>
        {error ? <ErrorState text={error} /> : null}
        {loading ? <LoadingState text="账号加载中" /> : visibleAccounts.length === 0 ? (
          <EmptyState text="暂无运营账号，点击左侧「添加运营账号」" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head account-row account-row-v2">
              <span>备注名</span><span>ID</span><span>平台</span><span>业务类型</span><span>使用状态</span><span>登录态</span><span>运营</span><span>Profile</span>
            </div>
            {visibleAccounts.map((account) => (
              <button key={account.id} type="button" className={`table-row account-row account-row-v2 ${selected?.id === account.id ? 'selected' : ''}`} onClick={() => chooseAccount(account)}>
                <span className="strong">{account.display_name}</span>
                <span>{account.id.slice(0, 8)}...</span>
                <span>{account.platform}</span>
                <span>{account.business_account_type_name || '未设置'}</span>
                <span>{labelUsageStatus(account.usage_status)}</span>
                <span><span className={`auth-pill ${authPillClassForAccount(account)}`}>{labelAccountLoginBadge(account)}</span></span>
                <span>{account.employee_display_name || '—'}</span>
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
      </aside>
    </section>
  );
}
