import { ExternalLink, Play, RefreshCw, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { fetchOptions } from '../api/options';
import { listAccounts, listAgents, listBehaviorProfiles, listBenchmarkGroupBusinessTypes, listBenchmarkGroups, listBusinessAccountTypes, listBusinessTypeRuleSets, listKeywordRuleSets, listNetworkEgressProfiles, listRiskPolicies } from '../api/resources';
import { formatAgentCapabilities } from '../utils/agentCapabilities';
import type { LocalAgent } from '../types/api';
import { createTaskTemplate, getTaskRun, getTaskTemplate, getTaskTemplateReadiness, listTaskTemplateRuns, listTaskTemplates, runTaskTemplate, type TaskFormData, type TaskTemplateType, updateTaskTemplate } from '../api/tasks';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { ApiError, BehaviorProfile, BenchmarkGroup, KeywordRuleSet, NetworkEgressProfile, PlatformAccount, ProductOptions, RiskPolicy, Role, TaskRun, TaskTemplateDetail, TaskTemplateListItem, TaskTemplateReadiness } from '../types/api';

type Props = {
  role: Role;
  userId: string;
  onOpenOperations?: (taskRunId?: string) => void;
};

type ResourceState = {
  accounts: PlatformAccount[];
  agents: LocalAgent[];
  ruleSets: KeywordRuleSet[];
  ruleSetIdsByBusinessType: Record<string, string[]>;
  behaviorProfiles: BehaviorProfile[];
  networkProfiles: NetworkEgressProfile[];
  riskPolicies: RiskPolicy[];
  benchmarkGroups: BenchmarkGroup[];
  benchmarkGroupIdsByBusinessType: Record<string, string[]>;
};

const emptyResources: ResourceState = {
  accounts: [],
  agents: [],
  ruleSets: [],
  ruleSetIdsByBusinessType: {},
  behaviorProfiles: [],
  networkProfiles: [],
  riskPolicies: [],
  benchmarkGroups: [],
  benchmarkGroupIdsByBusinessType: {},
};

const TASK_TYPE_META: Record<TaskTemplateType, { title: string; description: string }> = {
  recommendation_feed_task: {
    title: '推荐流采集',
    description: '用于采集平台推荐流内容，适合发现新趋势、新选题和潜在素材。',
  },
  creator_monitor_task: {
    title: '对标账号监控',
    description: '用于按对标组持续监控指定创作者，拉取其最新发布内容。',
  },
  keyword_search_task: {
    title: '关键词搜索采集',
    description: '用于按关键词主动检索内容，适合专题调研与定向线索补充。',
  },
};

const defaults: Record<TaskTemplateType, TaskFormData> = {
  recommendation_feed_task: {
    name: '推荐页巡检',
    enabled: true,
    executor_account_id: '',
    feed_type: 'xhs_home_feed',
    target_count: 50,
    refresh_rounds: 2,
    per_round_scroll_target: 50,
  },
  creator_monitor_task: {
    name: '对标账号监控',
    enabled: true,
    executor_account_id: '',
    benchmark_group_id: '',
    auto_detail_fetch: true,
  },
  keyword_search_task: {
    name: '关键词搜索',
    enabled: true,
    executor_account_id: '',
    platform: 'xhs',
    keywords: ['论文'],
    max_items: 50,
  },
};

export function TasksPage({ role, userId, onOpenOperations }: Props) {
  const [options, setOptions] = useState<ProductOptions | null>(null);
  const [resources, setResources] = useState<ResourceState>(emptyResources);
  const [templates, setTemplates] = useState<TaskTemplateListItem[]>([]);
  const [selectedType, setSelectedType] = useState<TaskTemplateType>('recommendation_feed_task');
  const [selected, setSelected] = useState<TaskTemplateDetail | null>(null);
  const [form, setForm] = useState<TaskFormData>(defaults.recommendation_feed_task);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [runLoading, setRunLoading] = useState(false);
  const [readiness, setReadiness] = useState<TaskTemplateReadiness | null>(null);
  const [activeRun, setActiveRun] = useState<TaskRun | null>(null);
  const [recentRuns, setRecentRuns] = useState<TaskRun[]>([]);
  const readonly = role === 'operator';
  const selectedTypeMeta = TASK_TYPE_META[selectedType];

  const agentById = useMemo(() => new Map(resources.agents.map((item) => [item.id, item])), [resources.agents]);
  const accountOptions = useMemo(() => resources.accounts.map((item) => {
    const agent = item.default_agent_id ? agentById.get(item.default_agent_id) : undefined;
    const agentSummary = agent
      ? `${agent.device_name || agent.id} · ${agent.status} · ${formatAgentCapabilities(agent.capabilities)}`
      : item.default_agent_device_name
        ? `${item.default_agent_device_name}（详情请到 Agent 管理查看）`
        : '未绑定 Agent';
    return {
      value: item.id,
      label: item.display_name,
      description: [item.platform, item.employee_display_name, item.session_health_status, agentSummary].filter(Boolean).join(' / '),
    };
  }), [resources.accounts, agentById]);
  const selectedAccount = useMemo(() => resources.accounts.find((item) => item.id === form.executor_account_id), [resources.accounts, form.executor_account_id]);
  const ruleSetOptions = useMemo(() => {
    const businessTypeId = selectedAccount?.business_account_type_id;
    if (!businessTypeId) return [];
    const allowedIds = new Set(resources.ruleSetIdsByBusinessType[businessTypeId] || []);
    return resources.ruleSets
      .filter((item) => allowedIds.has(item.id))
      .map((item) => ({ value: item.id, label: item.name, description: item.rule_scope }));
  }, [resources.ruleSets, resources.ruleSetIdsByBusinessType, selectedAccount?.business_account_type_id]);
  const behaviorOptions = useMemo(() => resources.behaviorProfiles.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [resources.behaviorProfiles]);
  const networkOptions = useMemo(() => resources.networkProfiles.map((item) => ({ value: item.id, label: item.name, description: item.strategy })), [resources.networkProfiles]);
  const riskOptions = useMemo(() => resources.riskPolicies.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [resources.riskPolicies]);
  const benchmarkOptions = useMemo(() => {
    const businessTypeId = selectedAccount?.business_account_type_id;
    if (!businessTypeId) return [];
    const allowedIds = new Set(resources.benchmarkGroupIdsByBusinessType[businessTypeId] || []);
    return resources.benchmarkGroups
      .filter((item) => allowedIds.has(item.id))
      .map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' }));
  }, [resources.benchmarkGroups, resources.benchmarkGroupIdsByBusinessType, selectedAccount?.business_account_type_id]);

  useEffect(() => {
    fetchOptions(role, userId).then(setOptions).catch((err) => setError(err.message));
    void reloadTemplates();
    void reloadResources();
  }, [role, userId]);

  async function reloadResources() {
    try {
      const [accounts, agents, ruleSets, businessTypes, behaviorProfiles, networkProfiles, riskPolicies, benchmarkGroups] = await Promise.all([
        listAccounts(role, userId),
        listAgents(role, userId),
        listKeywordRuleSets(role, userId),
        listBusinessAccountTypes(role, userId),
        listBehaviorProfiles(role, userId),
        listNetworkEgressProfiles(role, userId),
        listRiskPolicies(role, userId),
        listBenchmarkGroups(role, userId),
      ]);
      const bindingRows = await Promise.all(businessTypes.map((item) => listBusinessTypeRuleSets(role, item.id, userId)));
      const ruleSetIdsByBusinessType = Object.fromEntries(
        businessTypes.map((item, index) => [item.id, bindingRows[index].map((binding) => binding.rule_set_id)]),
      );
      const benchmarkBindingRows = await Promise.all(benchmarkGroups.map((item) => listBenchmarkGroupBusinessTypes(role, item.id, userId)));
      const benchmarkGroupIdsByBusinessType: Record<string, string[]> = {};
      for (const binding of benchmarkBindingRows.flat()) {
        benchmarkGroupIdsByBusinessType[binding.business_account_type_id] = [
          ...(benchmarkGroupIdsByBusinessType[binding.business_account_type_id] || []),
          binding.benchmark_group_id,
        ];
      }
      setResources({ accounts, agents, ruleSets, ruleSetIdsByBusinessType, behaviorProfiles, networkProfiles, riskPolicies, benchmarkGroups, benchmarkGroupIdsByBusinessType });
    } catch (err) {
      setError(err instanceof Error ? err.message : '资源选项加载失败');
    }
  }

  async function reloadTemplates() {
    setLoading(true);
    try {
      setTemplates(await listTaskTemplates(role, userId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '任务模板加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function openTemplate(templateId: string) {
    setActiveRun(null);
    setReadiness(null);
    setRecentRuns([]);
    const detail = await getTaskTemplate(role, templateId, userId);
    setSelected(detail);
    setSelectedType(detail.template_type as TaskTemplateType);
    setForm({ ...(detail.typed_payload as TaskFormData), name: detail.name, enabled: detail.enabled });
    await reloadRunContext(templateId);
  }

  function startCreate(type: TaskTemplateType) {
    setSelected(null);
    setActiveRun(null);
    setReadiness(null);
    setRecentRuns([]);
    setSelectedType(type);
    setForm(defaults[type]);
  }

  function setField<K extends keyof TaskFormData>(key: K, value: TaskFormData[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  useEffect(() => {
    if (!form.rule_set_id) return;
    if (!selectedAccount) return;
    if (ruleSetOptions.length === 0) return;
    if (ruleSetOptions.some((item) => item.value === form.rule_set_id)) return;
    setField('rule_set_id', '');
  }, [form.executor_account_id, form.rule_set_id, ruleSetOptions, selectedAccount]);

  useEffect(() => {
    if (selectedType !== 'creator_monitor_task' || !form.benchmark_group_id) return;
    if (benchmarkOptions.some((item) => item.value === form.benchmark_group_id)) return;
    setField('benchmark_group_id', '');
  }, [benchmarkOptions, form.benchmark_group_id, form.executor_account_id, selectedType]);

  async function saveTemplate() {
    setError('');
    setToast('');
    try {
      const payload = normalizePayload(selectedType, form);
      const detail = selected
        ? await updateTaskTemplate(role, selectedType, selected.id, payload, userId)
        : await createTaskTemplate(role, selectedType, payload, userId);
      setSelected(detail);
      await reloadTemplates();
      await reloadRunContext(detail.id);
      setToast('模板已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  }

  async function runSelected() {
    if (!selected) return;
    setError('');
    setToast('');
    setRunLoading(true);
    try {
      const result = await runTaskTemplate(role, selected.id, userId);
      setToast(`已创建 ${result.jobs_created} 个 Job，等待 Agent 执行`);
      const detail = await getTaskRun(role, result.task_run_id, userId);
      setActiveRun(detail);
      await reloadRecentRuns(selected.id);
    } catch (err) {
      setError(readableRunError(err));
      const apiError = err as ApiError;
      const readinessDetail = extractReadiness(apiError.detail);
      if (readinessDetail) setReadiness(readinessDetail);
      setToast('运行请求失败，请查看原因');
    } finally {
      setRunLoading(false);
    }
  }

  async function reloadRunContext(templateId: string) {
    try {
      const [ready, runs] = await Promise.all([
        getTaskTemplateReadiness(role, templateId, userId),
        listTaskTemplateRuns(role, templateId, userId),
      ]);
      setReadiness(ready);
      setRecentRuns(runs.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行上下文加载失败');
    }
  }

  async function reloadRecentRuns(templateId: string) {
    const runs = await listTaskTemplateRuns(role, templateId, userId);
    setRecentRuns(runs.items);
  }

  useEffect(() => {
    if (!activeRun || ['success', 'partial_success', 'failed'].includes(activeRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getTaskRun(role, activeRun.id, userId);
        setActiveRun(next);
        if (selected) await reloadRecentRuns(selected.id);
      } catch (err) {
        setError(err instanceof Error ? err.message : '运行状态刷新失败');
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeRun?.id, activeRun?.status, role, userId, selected?.id]);

  return (
    <section className="page-grid tasks-grid">
      <aside className="filter-panel">
        <div className="panel-title">任务类型</div>
        {(['recommendation_feed_task', 'creator_monitor_task', 'keyword_search_task'] as TaskTemplateType[]).map((type) => (
          <button key={type} className={`type-tab ${selectedType === type ? 'active' : ''}`} onClick={() => startCreate(type)}>
            {TASK_TYPE_META[type].title}
          </button>
        ))}
        <div className="scheduler-note">
          周期调度由后台 materialization 入口生成。当前页面支持手动触发任务模板。
        </div>
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>情报任务中心</h1>
            <span>模板配置与手动执行</span>
          </div>
          <button className="secondary" onClick={reloadTemplates}><RefreshCw size={14} />刷新</button>
        </div>
        {toast && <div className="toast">{toast}</div>}
        {error && <ErrorState text={error} />}
        {loading ? <LoadingState text="任务模板加载中" /> : templates.length === 0 ? <EmptyState text="暂无任务模板" /> : (
          <div className="data-table">
            <div className="table-row table-head task-head"><span>名称</span><span>类型</span><span>启用</span><span>执行账号</span><span>关键字段</span></div>
            {templates.map((template) => (
              <button key={template.id} className={`table-row task-row ${selected?.id === template.id ? 'selected' : ''}`} onClick={() => openTemplate(template.id)}>
                <span className="strong">{template.name}</span>
                <span>{template.template_type}</span>
                <span>{template.enabled ? '启用' : '停用'}</span>
                <span>{resourceName(resources.accounts, template.account_id) || '-'}</span>
                <span>{Object.entries(template.key_fields).map(([key, value]) => `${key}:${Array.isArray(value) ? value.join('/') : value}`).join('  ')}</span>
              </button>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        <div className="panel-title">{selected ? '编辑模板' : '新建模板'}</div>
        <div className="form-stack" data-testid="dynamic-task-form">
          <div className="detail-section">
            <b>{selectedTypeMeta.title}</b>
            <span className="muted-hint">{selectedTypeMeta.description}</span>
          </div>
          <label htmlFor="task-template-type">模板类型</label>
          <select id="task-template-type" value={selectedType} onChange={(event) => startCreate(event.target.value as TaskTemplateType)} disabled={!!selected}>
            {options?.task_template_types.map((item) => (
              <option key={item.value} value={item.value}>
                {TASK_TYPE_META[item.value as TaskTemplateType]?.title || item.label}
              </option>
            ))}
          </select>
          <label>名称</label>
          <input value={form.name} onChange={(event) => setField('name', event.target.value)} />
          <ResourceSelect label="执行账号" testId="executor-account-select" value={form.executor_account_id} options={accountOptions} onChange={(value) => setField('executor_account_id', value)} />
          <label className="check-line"><input type="checkbox" checked={form.enabled} onChange={(event) => setField('enabled', event.target.checked)} />启用</label>
          {selectedType === 'recommendation_feed_task' && (
            <>
              <label>Feed Type</label>
              <select value={form.feed_type || ''} onChange={(event) => setField('feed_type', event.target.value)}>
                {options?.feed_types.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <label>目标数量</label>
              <input type="number" value={form.target_count || 50} onChange={(event) => setField('target_count', Number(event.target.value))} />
              <label>刷新轮数</label>
              <input type="number" value={form.refresh_rounds || 2} onChange={(event) => setField('refresh_rounds', Number(event.target.value))} />
              <label>每轮滚动目标</label>
              <input type="number" value={form.per_round_scroll_target || 50} onChange={(event) => setField('per_round_scroll_target', Number(event.target.value))} />
            </>
          )}
          {selectedType === 'creator_monitor_task' && (
            <>
              <ResourceSelect label="对标组" testId="benchmark-group-select" value={form.benchmark_group_id} options={benchmarkOptions} onChange={(value) => setField('benchmark_group_id', value)} />
              {form.executor_account_id && benchmarkOptions.length === 0 && (
                <div className="inline-error">当前执行账号的业务类型尚未绑定对标账号组，请先到对标账号组管理中绑定。</div>
              )}
              <label className="check-line"><input type="checkbox" checked={form.auto_detail_fetch !== false} onChange={(event) => setField('auto_detail_fetch', event.target.checked)} />自动补详情</label>
            </>
          )}
          {selectedType === 'keyword_search_task' && (
            <>
              <label>平台</label>
              <select value={form.platform || 'xhs'} onChange={(event) => setField('platform', event.target.value)}>
                {options?.platforms.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <label>关键词</label>
              <input value={(form.keywords || []).join(',')} onChange={(event) => setField('keywords', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))} />
              <label>最大采样</label>
              <input type="number" value={form.max_items || 50} onChange={(event) => setField('max_items', Number(event.target.value))} />
            </>
          )}
          <ResourceSelect label="入库规则" testId="rule-set-select" value={form.rule_set_id} options={ruleSetOptions} onChange={(value) => setField('rule_set_id', value)} />
          {form.executor_account_id && ruleSetOptions.length === 0 && (
            <div className="inline-error">当前执行账号的业务类型尚未绑定入库规则，请先到规则管理详情中绑定。</div>
          )}
          <ResourceSelect label="行为策略" testId="behavior-profile-select" value={form.behavior_profile_id} options={behaviorOptions} onChange={(value) => setField('behavior_profile_id', value)} />
          <ResourceSelect label="网络出口策略" testId="network-profile-select" value={form.network_egress_profile_id} options={networkOptions} onChange={(value) => setField('network_egress_profile_id', value)} />
          <ResourceSelect label="风险策略" testId="risk-policy-select" value={form.risk_policy_id} options={riskOptions} onChange={(value) => setField('risk_policy_id', value)} />
          <div className="action-strip">
            <button onClick={saveTemplate} disabled={readonly}><Save size={14} />保存</button>
            <button onClick={runSelected} disabled={!selected || readonly || runLoading || (readiness ? !readiness.ready : false)}><Play size={14} />{runLoading ? '运行中' : '立即运行'}</button>
          </div>
          {readonly && <div className="inline-error">operator 当前按后端权限只读任务中心。</div>}
          {selected && readiness && <ReadinessCard readiness={readiness} />}
          {activeRun && <TaskRunPanel run={activeRun} onOpenOperations={onOpenOperations} />}
          {recentRuns.length > 0 && <RecentRuns runs={recentRuns} onSelect={async (run) => setActiveRun(await getTaskRun(role, run.id, userId))} />}
        </div>
      </aside>
    </section>
  );
}

function resourceName(items: PlatformAccount[], id?: string | null) {
  return items.find((item) => item.id === id)?.display_name || id;
}

function normalizePayload(type: TaskTemplateType, form: TaskFormData): TaskFormData {
  const base = clean({
    name: form.name,
    enabled: form.enabled,
    executor_account_id: form.executor_account_id,
    rule_set_id: form.rule_set_id,
    behavior_profile_id: form.behavior_profile_id,
    network_egress_profile_id: form.network_egress_profile_id,
    risk_policy_id: form.risk_policy_id,
  });
  if (type === 'recommendation_feed_task') {
    return clean({ ...base, feed_type: form.feed_type, target_count: form.target_count, refresh_rounds: form.refresh_rounds, per_round_scroll_target: form.per_round_scroll_target });
  }
  if (type === 'creator_monitor_task') {
    return clean({ ...base, benchmark_group_id: form.benchmark_group_id, auto_detail_fetch: form.auto_detail_fetch });
  }
  return clean({ ...base, platform: form.platform, keywords: form.keywords, max_items: form.max_items });
}

function clean<T extends Record<string, unknown>>(value: T): T {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== '' && item !== undefined)) as T;
}

function ReadinessCard({ readiness }: { readiness: TaskTemplateReadiness }) {
  return (
    <div className={`run-result ${readiness.ready ? 'ready' : 'blocked'}`} data-testid="readiness-card">
      <b>{readiness.ready ? '可立即运行' : '当前不可运行'}</b>
      {readiness.checks.map((check) => (
        <div key={check.key} className={check.ok ? 'check-ok' : 'check-bad'}>{check.ok ? '通过' : '阻塞'} · {check.message}</div>
      ))}
    </div>
  );
}

function TaskRunPanel({ run, onOpenOperations }: { run: TaskRun; onOpenOperations?: (taskRunId?: string) => void }) {
  const summary = runSummaryText(run);
  const queue = run.queue_context;
  const queueHint = queue && ['queued', 'materialized', 'running'].includes(run.status) ? queue.message : '';
  const searchSummary = run.result_summary.keyword_search as Record<string, unknown> | undefined;
  return (
    <div className="run-result" data-testid="task-run-panel">
      <b>本次运行 · {statusLabel(run.status)}</b>
      <div>task_run_id: <code>{run.id}</code></div>
      <div>创建时间: {formatTime(run.created_at)}</div>
      <div>生成 Job 数: {run.jobs_total}</div>
      <div>Job 状态: pending {run.jobs_pending} / running {run.jobs_running} / success {run.jobs_success} / failed {run.jobs_failed}</div>
      {queueHint && <div className="queue-hint" data-testid="queue-hint">{queueHint}</div>}
      {queue?.agent_running_job_type && <div>Agent 当前任务：{queue.agent_running_job_type}</div>}
      {typeof queue?.pending_jobs_ahead === 'number' && queue.pending_jobs_ahead > 0 && <div>前方排队：{queue.pending_jobs_ahead} 个 Job</div>}
      {typeof queue?.job_priority === 'number' && <div>本 Job 优先级：{queue.job_priority}</div>}
      {queue && queue.pending_jobs_ahead > 5 ? <div className="queue-hint">等待较久可前往运行中心查看队列</div> : null}
      {onOpenOperations && (
        <button type="button" className="inline-link" onClick={() => onOpenOperations(run.id)} data-testid="open-operations">
          <ExternalLink size={13} />查看运行详情
        </button>
      )}
      {(summary || searchSummary?.message) ? <div>{String(summary || searchSummary?.message || '')}</div> : null}
      {['success', 'partial_success'].includes(run.status) && <a className="inline-link" href="/intelligence"><ExternalLink size={13} />去情报中心查看</a>}
      <div className="mini-list">
        {run.jobs.map((job) => (
          <div className="mini-row passive" key={job.job_id}>
            <b>{job.job_type}</b>
            <span>{statusLabel(job.status)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecentRuns({ runs, onSelect }: { runs: TaskRun[]; onSelect: (run: TaskRun) => void }) {
  return (
    <div className="run-result" data-testid="recent-runs">
      <b>最近运行记录</b>
      {runs.slice(0, 5).map((run) => (
        <button className="mini-row" key={run.id} onClick={() => onSelect(run)}>
          <span>{formatTime(run.created_at)}</span>
          <b>{statusLabel(run.status)}</b>
          <span>{runSummaryText(run) || `${run.jobs_total} 个 Job`}</span>
        </button>
      ))}
    </div>
  );
}

function runSummaryText(run: TaskRun) {
  const feed = run.result_summary.feed_collect as Record<string, unknown> | undefined;
  const creator = run.result_summary.creator_monitor as Record<string, unknown> | undefined;
  const search = run.result_summary.keyword_search as Record<string, unknown> | undefined;
  return String(feed?.message || creator?.message || search?.message || '');
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    materialized: '已物化',
    queued: '排队中',
    pending: '等待中',
    claimed: '已领取',
    running: '执行中',
    success: '成功',
    partial_success: '部分成功',
    failed: '失败',
  };
  return labels[status] || status;
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function readableRunError(err: unknown) {
  const apiError = err as ApiError;
  const readiness = extractReadiness(apiError.detail);
  if (readiness?.messages?.length) return readiness.messages.join('；');
  return err instanceof Error ? err.message : '运行失败';
}

function extractReadiness(detail: unknown): TaskTemplateReadiness | null {
  if (!detail || typeof detail !== 'object') return null;
  const maybe = detail as { detail?: unknown; ready?: unknown; checks?: unknown; messages?: unknown };
  const body = typeof maybe.detail === 'object' && maybe.detail ? maybe.detail as { ready?: unknown; checks?: unknown; messages?: unknown } : maybe;
  if (typeof body.ready === 'boolean' && Array.isArray(body.checks)) {
    return { ready: body.ready, checks: body.checks as TaskTemplateReadiness['checks'], messages: Array.isArray(body.messages) ? body.messages as string[] : [] };
  }
  return null;
}
