import { RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { listAccounts, listAgents, listEmployees, updateAgent } from '../api/resources';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import { agentCapabilityKind, formatAgentCapabilities, formatAgentDeviceLabel, formatAgentHeartbeat, isAgentLive } from '../utils/agentCapabilities';
import type { Employee, LocalAgent, PlatformAccount, Role } from '../types/api';

type Props = { role: Role; userId: string };

function canManageAgentBinding(role: Role) {
  return role === 'admin' || role === 'supervisor';
}

export function AgentsPage({ role, userId }: Props) {
  const [agents, setAgents] = useState<LocalAgent[]>([]);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selected, setSelected] = useState<LocalAgent | null>(null);
  const [bindEmployeeId, setBindEmployeeId] = useState('');
  const [binding, setBinding] = useState(false);
  const [bindError, setBindError] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const manageBinding = canManageAgentBinding(role);

  const boundCount = useMemo(() => {
    const result = new Map<string, number>();
    accounts.forEach((account) => {
      if (account.default_agent_id) result.set(account.default_agent_id, (result.get(account.default_agent_id) || 0) + 1);
    });
    return result;
  }, [accounts]);

  const employeeOptions = useMemo(
    () => employees.map((item) => ({ value: item.id, label: item.display_name, description: item.user_username || undefined })),
    [employees],
  );

  useEffect(() => { void reload(); }, [role, userId]);

  useEffect(() => {
    setBindEmployeeId(selected?.employee_id || '');
    setBindError('');
  }, [selected?.id, selected?.employee_id]);

  async function reload() {
    setLoading(true);
    setError('');
    try {
      const [nextAgents, nextAccounts, nextEmployees] = await Promise.all([
        listAgents(role, userId),
        listAccounts(role, userId),
        manageBinding ? listEmployees(role, userId) : Promise.resolve([] as Employee[]),
      ]);
      const sortedAgents = [...nextAgents].sort((left, right) => {
        const leftTime = left.last_heartbeat_at ? Date.parse(left.last_heartbeat_at) : 0;
        const rightTime = right.last_heartbeat_at ? Date.parse(right.last_heartbeat_at) : 0;
        return rightTime - leftTime;
      });
      setAgents(sortedAgents);
      setAccounts(nextAccounts);
      setEmployees(nextEmployees);
      setSelected((current) => {
        if (!current) return sortedAgents[0] || null;
        return sortedAgents.find((item) => item.id === current.id) || sortedAgents[0] || null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent 加载失败');
    } finally {
      setLoading(false);
    }
  }

  function chooseAgent(agent: LocalAgent) {
    setSelected(agent);
  }

  async function saveEmployeeBinding() {
    if (!selected || !manageBinding) return;
    setBinding(true);
    setBindError('');
    try {
      const updated = await updateAgent(role, selected.id, { employee_id: bindEmployeeId || null }, userId);
      setAgents((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelected(updated);
    } catch (err) {
      setBindError(err instanceof Error ? err.message : '绑定员工失败');
    } finally {
      setBinding(false);
    }
  }

  const bindingDirty = Boolean(selected) && (bindEmployeeId || '') !== (selected?.employee_id || '');
  const canRetireSelected = Boolean(selected && manageBinding && !isAgentLive(selected) && selected.status !== 'retired');

  async function retireSelectedAgent() {
    if (!selected || !manageBinding) return;
    setBinding(true);
    setBindError('');
    try {
      const updated = await updateAgent(role, selected.id, { status: 'retired' }, userId);
      setAgents((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setSelected(updated);
    } catch (err) {
      setBindError(err instanceof Error ? err.message : '停用 Agent 失败');
    } finally {
      setBinding(false);
    }
  }

  return (
    <section className="page-grid two-col-grid">
      <section className="list-panel">
        <div className="section-head">
          <div><h1>Agent 管理</h1><span>{agents.length} 台本地 Agent</span></div>
          <button className="secondary" onClick={reload}><RefreshCw size={14} />刷新</button>
        </div>
        {error && <ErrorState text={error} />}
        {loading ? <LoadingState text="Agent 加载中" /> : agents.length === 0 ? <EmptyState text="暂无 Agent" /> : (
          <div className="data-table">
            <div className="table-row table-head agent-row"><span>设备</span><span>所属员工</span><span>类型</span><span>状态</span><span>版本</span><span>最近心跳</span><span>能力</span><span>绑定账号</span></div>
            {agents.map((agent) => (
              <button key={agent.id} className={`table-row agent-row ${selected?.id === agent.id ? 'selected' : ''}`} onClick={() => chooseAgent(agent)}>
                <span className="strong">{formatAgentDeviceLabel(agent)}</span>
                <span>{agent.employee_display_name || '未绑定'}</span>
                <span><b className="tag">{agentCapabilityKind(agent.capabilities) === 'runtime_v1' ? 'Runtime V1' : agentCapabilityKind(agent.capabilities) === 'legacy' ? '旧脚本' : '未知'}</b></span>
                <span><b className="tag">{agent.status}</b></span><span>{agent.agent_version || '-'}</span><span>{formatAgentHeartbeat(agent)}</span><span>{formatAgentCapabilities(agent.capabilities)}</span><span>{boundCount.get(agent.id) || 0}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        <div className="panel-title">Agent 详情</div>
        {!selected ? <EmptyState text="选择一台 Agent" /> : (
          <div className="detail-body">
            <div className="detail-title">{formatAgentDeviceLabel(selected)}</div>
            <div className="meta-line">{selected.status} · {selected.agent_version || '-'} · {agentCapabilityKind(selected.capabilities) === 'runtime_v1' ? 'Runtime V1' : agentCapabilityKind(selected.capabilities) === 'legacy' ? '旧脚本 Agent' : '能力未识别'}</div>
            <dl className="metric-grid">
              <div><dt>Agent ID</dt><dd><code>{selected.id}</code></dd></div>
              <div><dt>machine_fingerprint</dt><dd><code>{selected.machine_fingerprint || '-'}</code></dd></div>
              <div><dt>所属员工</dt><dd>{selected.employee_display_name || '未绑定'}</dd></div>
              <div><dt>绑定账号</dt><dd>{boundCount.get(selected.id) || 0}</dd></div>
              <div><dt>最近心跳</dt><dd>{formatAgentHeartbeat(selected)}</dd></div>
              <div><dt>状态</dt><dd>{selected.status}</dd></div>
            </dl>
            {manageBinding && (
              <div className="detail-section form-stack">
                <b>绑定运营员工</b>
                <p className="login-hint">本机只需运行 Local Agent；员工归属在此选择并保存，无需改本地配置文件。</p>
                <ResourceSelect
                  label="运营员工"
                  testId="agent-bind-employee-select"
                  value={bindEmployeeId}
                  options={employeeOptions}
                  onChange={setBindEmployeeId}
                />
                {bindError && <ErrorState text={bindError} />}
                <button className="primary" type="button" disabled={binding || !bindingDirty} onClick={() => void saveEmployeeBinding()}>
                  {binding ? '保存中…' : '保存员工绑定'}
                </button>
                {canRetireSelected ? (
                  <button className="secondary" type="button" disabled={binding} onClick={() => void retireSelectedAgent()}>
                    停用离线历史 Agent
                  </button>
                ) : null}
              </div>
            )}
            <div className="detail-section">
              <b>Capabilities</b>
              <pre className="json-box">{JSON.stringify(selected.capabilities || {}, null, 2)}</pre>
            </div>
          </div>
        )}
      </aside>
    </section>
  );
}
