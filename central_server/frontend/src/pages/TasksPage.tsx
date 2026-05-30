import { ExternalLink, Play, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchOptions } from '../api/options';
import { listAccounts, listAgents, listBehaviorProfiles, listBusinessAccountTypes, listBusinessTypeBenchmarkGroups, listBusinessTypeRuleSets, listNetworkEgressProfiles, listRiskPolicies } from '../api/resources';
import { formatAgentCapabilities } from '../utils/agentCapabilities';
import type { LocalAgent } from '../types/api';
import {
  createTaskSchedule,
  createTaskTemplate,
  deleteTaskTemplate,
  getTaskRun,
  getTaskTemplate,
  getTaskTemplateReadiness,
  getTaskTemplateRunReadiness,
  listTaskTemplates,
  listTemplateSchedules,
  runTaskTemplate,
  type TaskFormData,
  type TaskScheduleFormData,
  type TaskTemplateType,
  updateTaskTemplate,
} from '../api/tasks';
import { ResourceSelect } from '../components/ResourceSelect';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { ApiError, BehaviorProfile, BusinessAccountType, BusinessAccountTypeBenchmarkGroup, BusinessAccountTypeRuleSet, NetworkEgressProfile, PlatformAccount, ProductOptions, RiskPolicy, Role, TaskRun, TaskSchedule, TaskTemplateDetail, TaskTemplateListItem, TaskTemplateReadiness } from '../types/api';
import { useTaskRunRefresh, useTaskRunRefreshEffect } from '../context/TaskRunRefreshContext';
import { accountOptionsForRun, canCreateTaskTemplate, canDeleteTemplate, canEditTemplate, canScheduleTemplate } from '../utils/taskTemplatePermissions';

type Props = {
  role: Role;
  userId: string;
  onOpenOperations?: (taskRunId?: string) => void;
};

type ResourceState = {
  accounts: PlatformAccount[];
  agents: LocalAgent[];
  businessTypes: BusinessAccountType[];
  ruleSetBindingsByBusinessType: Record<string, BusinessAccountTypeRuleSet[]>;
  benchmarkGroupBindingsByBusinessType: Record<string, BusinessAccountTypeBenchmarkGroup[]>;
  behaviorProfiles: BehaviorProfile[];
  networkProfiles: NetworkEgressProfile[];
  riskPolicies: RiskPolicy[];
};

const emptyResources: ResourceState = {
  accounts: [],
  agents: [],
  businessTypes: [],
  ruleSetBindingsByBusinessType: {},
  benchmarkGroupBindingsByBusinessType: {},
  behaviorProfiles: [],
  networkProfiles: [],
  riskPolicies: [],
};

const TASK_TEMPLATE_TYPES: TaskTemplateType[] = ['recommendation_feed_task', 'creator_monitor_task', 'keyword_search_task'];

type TaskTypeFilter = TaskTemplateType | 'all';

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
    business_account_type_id: '',
    enabled: true,
    feed_type: 'xhs_home_feed',
    target_count: 50,
    refresh_rounds: 2,
    per_round_scroll_target: 50,
  },
  creator_monitor_task: {
    name: '对标账号监控',
    business_account_type_id: '',
    enabled: true,
    benchmark_group_id: '',
    auto_detail_fetch: true,
  },
  keyword_search_task: {
    name: '关键词搜索',
    business_account_type_id: '',
    enabled: true,
    platform: 'xhs',
    keywords: ['论文'],
    max_items: 50,
  },
};

const emptyScheduleForm: TaskScheduleFormData = {
  schedule_type: 'interval_seconds',
  interval_seconds: 3600,
  executor_account_id: '',
  enabled: true,
};

const KEY_FIELD_LABELS: Record<string, string> = {
  feed_type: 'Feed',
  target_count: '目标数',
  benchmark_group_id: '对标组',
  platform: '平台',
  keywords: '关键词',
  max_items: '采样上限',
  rule_set_id: '规则集',
};

function formatTemplateTypeLabel(type: string): string {
  return TASK_TYPE_META[type as TaskTemplateType]?.title || type;
}

function formatTemplateKeyFields(keyFields: Record<string, unknown>): string {
  const parts = Object.entries(keyFields).map(([key, value]) => {
    const label = KEY_FIELD_LABELS[key] || key;
    const text = Array.isArray(value) ? value.join('、') : String(value ?? '');
    return `${label} ${text}`;
  });
  return parts.length > 0 ? parts.join(' · ') : '-';
}

function buildFormFromDetail(detail: TaskTemplateDetail): TaskFormData {
  const type = detail.template_type as TaskTemplateType;
  const config = { ...(detail.config || {}) } as Record<string, unknown>;
  delete config.executor_account_id;
  const typed = (detail.typed_payload || {}) as Partial<TaskFormData>;
  return {
    ...defaults[type],
    ...(config as Partial<TaskFormData>),
    ...typed,
    name: detail.name,
    enabled: detail.enabled,
    business_account_type_id: detail.business_account_type_id || '',
  };
}

export function TasksPage({ role, userId, onOpenOperations }: Props) {
  const taskRunRefresh = useTaskRunRefresh();
  const resourceLoadGeneration = useRef(0);
  const [options, setOptions] = useState<ProductOptions | null>(null);
  const [resources, setResources] = useState<ResourceState>(emptyResources);
  const [templates, setTemplates] = useState<TaskTemplateListItem[]>([]);
  const [typeFilter, setTypeFilter] = useState<TaskTypeFilter>('all');
  const [selectedType, setSelectedType] = useState<TaskTemplateType>('recommendation_feed_task');
  const [selected, setSelected] = useState<TaskTemplateDetail | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState<TaskFormData>(defaults.recommendation_feed_task);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [runLoading, setRunLoading] = useState(false);
  const [readiness, setReadiness] = useState<TaskTemplateReadiness | null>(null);
  const [runReadiness, setRunReadiness] = useState<TaskTemplateReadiness | null>(null);
  const [runExecutorAccountId, setRunExecutorAccountId] = useState('');
  const [activeRun, setActiveRun] = useState<TaskRun | null>(null);
  const [schedules, setSchedules] = useState<TaskSchedule[]>([]);
  const [scheduleForm, setScheduleForm] = useState<TaskScheduleFormData>(emptyScheduleForm);

  const selectedTypeMeta = TASK_TYPE_META[selectedType];
  const detailOpen = Boolean(selected) || isCreating;
  const editable = selected ? canEditTemplate(role, selected, userId) : canCreateTaskTemplate(role);
  const schedulable = canScheduleTemplate(role, selected, userId);
  const businessTypeId = form.business_account_type_id || selected?.business_account_type_id || '';

  const businessTypeOptions = useMemo(() => {
    if (role === 'operator') {
      const ids = new Set(resources.accounts.map((item) => item.business_account_type_id).filter(Boolean));
      return resources.businessTypes
        .filter((item) => ids.has(item.id))
        .map((item) => ({ value: item.id, label: item.name, description: item.description || undefined }));
    }
    return resources.businessTypes.map((item) => ({ value: item.id, label: item.name, description: item.description || undefined }));
  }, [resources.accounts, resources.businessTypes, role]);

  const runAccountOptions = useMemo(() => {
    return accountOptionsForRun(role, resources.accounts, businessTypeId).map((item) => {
      const agent = item.default_agent_id ? resources.agents.find((entry) => entry.id === item.default_agent_id) : undefined;
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
    });
  }, [resources.accounts, resources.agents, businessTypeId, role]);

  const ruleSetOptions = useMemo(() => {
    if (!businessTypeId) return [];
    return (resources.ruleSetBindingsByBusinessType[businessTypeId] || []).map((item) => ({
      value: item.rule_set_id,
      label: item.rule_set_name || item.rule_set_id,
      description: item.is_default ? '默认' : undefined,
    }));
  }, [resources.ruleSetBindingsByBusinessType, businessTypeId]);

  const behaviorOptions = useMemo(() => resources.behaviorProfiles.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [resources.behaviorProfiles]);
  const networkOptions = useMemo(() => resources.networkProfiles.map((item) => ({ value: item.id, label: item.name, description: item.strategy })), [resources.networkProfiles]);
  const riskOptions = useMemo(() => resources.riskPolicies.map((item) => ({ value: item.id, label: item.name, description: item.enabled ? '启用' : '停用' })), [resources.riskPolicies]);

  const benchmarkOptions = useMemo(() => {
    if (!businessTypeId) return [];
    return (resources.benchmarkGroupBindingsByBusinessType[businessTypeId] || []).map((item) => ({
      value: item.benchmark_group_id,
      label: item.benchmark_group_name || item.benchmark_group_id,
    }));
  }, [resources.benchmarkGroupBindingsByBusinessType, businessTypeId]);

  const templateCountByType = useMemo(() => {
    const counts: Record<string, number> = { all: templates.length };
    for (const template of templates) {
      counts[template.template_type] = (counts[template.template_type] || 0) + 1;
    }
    return counts;
  }, [templates]);

  const filteredTemplates = useMemo(() => {
    if (typeFilter === 'all') return templates;
    return templates.filter((template) => template.template_type === typeFilter);
  }, [templates, typeFilter]);

  const listPanelSubtitle = useMemo(() => {
    if (typeFilter === 'all') {
      return filteredTemplates.length > 0 ? `共 ${filteredTemplates.length} 个模板` : '模板配置与手动执行';
    }
    const label = TASK_TYPE_META[typeFilter].title;
    return filteredTemplates.length > 0 ? `${label} · ${filteredTemplates.length} 个` : `${label} · 暂无模板`;
  }, [filteredTemplates.length, typeFilter]);

  useEffect(() => {
    if (!selected) return;
    if (typeFilter !== 'all' && selected.template_type !== typeFilter) {
      setSelected(null);
      setIsCreating(false);
      setActiveRun(null);
      setReadiness(null);
      setRunReadiness(null);
      setRunExecutorAccountId('');
      setSchedules([]);
    }
  }, [typeFilter, selected]);

  useEffect(() => {
    fetchOptions(role, userId).then(setOptions).catch((err) => setError(err.message));
    void reloadTemplates();
    void reloadResources();
  }, [role, userId]);

  async function loadBindingsForBusinessTypes(businessTypeIds: string[]) {
    const uniqueIds = [...new Set(businessTypeIds.filter(Boolean))];
    if (uniqueIds.length === 0) {
      return { ruleSetBindingsByBusinessType: {}, benchmarkGroupBindingsByBusinessType: {} };
    }
    const rows = await Promise.all(
      uniqueIds.map(async (businessTypeId) => {
        const [ruleSets, benchmarkGroups] = await Promise.all([
          listBusinessTypeRuleSets(role, businessTypeId, userId),
          listBusinessTypeBenchmarkGroups(role, businessTypeId, userId),
        ]);
        return { businessTypeId, ruleSets, benchmarkGroups };
      }),
    );
    return {
      ruleSetBindingsByBusinessType: Object.fromEntries(rows.map((row) => [row.businessTypeId, row.ruleSets])),
      benchmarkGroupBindingsByBusinessType: Object.fromEntries(rows.map((row) => [row.businessTypeId, row.benchmarkGroups])),
    };
  }

  async function ensureBindingsForBusinessType(businessTypeId: string) {
    if (!businessTypeId) return;
    const bindings = await loadBindingsForBusinessTypes([businessTypeId]);
    setResources((current) => ({
      ...current,
      ruleSetBindingsByBusinessType: { ...current.ruleSetBindingsByBusinessType, ...bindings.ruleSetBindingsByBusinessType },
      benchmarkGroupBindingsByBusinessType: {
        ...current.benchmarkGroupBindingsByBusinessType,
        ...bindings.benchmarkGroupBindingsByBusinessType,
      },
    }));
  }

  async function reloadResources() {
    const generation = ++resourceLoadGeneration.current;
    try {
      const [accounts, agents, businessTypes, behaviorProfiles, networkProfiles, riskPolicies] = await Promise.all([
        listAccounts(role, userId),
        listAgents(role, userId),
        listBusinessAccountTypes(role, userId),
        listBehaviorProfiles(role, userId),
        listNetworkEgressProfiles(role, userId),
        listRiskPolicies(role, userId),
      ]);
      const scopedBusinessTypeIds =
        role === 'operator'
          ? [...new Set(accounts.map((item) => item.business_account_type_id).filter(Boolean) as string[])]
          : businessTypes.map((item) => item.id);
      const bindings = await loadBindingsForBusinessTypes(scopedBusinessTypeIds);
      if (generation !== resourceLoadGeneration.current) return;
      setResources({
        accounts,
        agents,
        businessTypes,
        ...bindings,
        behaviorProfiles,
        networkProfiles,
        riskPolicies,
      });
    } catch (err) {
      if (generation !== resourceLoadGeneration.current) return;
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

  async function reloadSchedules(templateId: string) {
    try {
      setSchedules(await listTemplateSchedules(role, templateId, userId));
    } catch {
      setSchedules([]);
    }
  }

  async function removeTemplate(template: TaskTemplateListItem) {
    if (!canDeleteTemplate(role, template, userId)) return;
    if (!window.confirm(`确认删除任务模板「${template.name}」？删除后将同时移除关联的定时调度与运行记录。`)) return;
    setError('');
    try {
      await deleteTaskTemplate(role, template.id, userId);
      if (selected?.id === template.id) {
        startCreate(template.template_type as TaskTemplateType);
      }
      await reloadTemplates();
      setToast('任务模板已删除');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除任务模板失败');
    }
  }

  async function openTemplate(templateId: string) {
    setIsCreating(false);
    resourceLoadGeneration.current += 1;
    setError('');
    setActiveRun(null);
    setReadiness(null);
    setRunReadiness(null);
    setRunExecutorAccountId('');
    try {
      const detail = await getTaskTemplate(role, templateId, userId);
      const type = detail.template_type as TaskTemplateType;
      setSelected(detail);
      setSelectedType(type);
      setForm(buildFormFromDetail(detail));
      await ensureBindingsForBusinessType(detail.business_account_type_id || '');
      void reloadRunContext(templateId);
      if (canScheduleTemplate(role, detail, userId)) {
        await reloadSchedules(templateId);
      } else {
        setSchedules([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '模板详情加载失败');
    }
  }

  function startCreate(type: TaskTemplateType) {
    setSelected(null);
    setIsCreating(true);
    setActiveRun(null);
    setReadiness(null);
    setRunReadiness(null);
    setRunExecutorAccountId('');
    setSchedules([]);
    setSelectedType(type);
    setForm({ ...defaults[type] });
  }

  function startNewTemplate() {
    const type = typeFilter === 'all' ? 'recommendation_feed_task' : typeFilter;
    startCreate(type);
  }

  function changeFormType(type: TaskTemplateType) {
    if (selected) return;
    setSelectedType(type);
    setForm({ ...defaults[type] });
  }

  function setField<K extends keyof TaskFormData>(key: K, value: TaskFormData[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  useEffect(() => {
    if (!form.rule_set_id || !businessTypeId) return;
    if (ruleSetOptions.length === 0) return;
    if (ruleSetOptions.some((item) => item.value === form.rule_set_id)) return;
    setField('rule_set_id', '');
  }, [businessTypeId, form.rule_set_id, ruleSetOptions]);

  useEffect(() => {
    if (selectedType !== 'creator_monitor_task' || !form.benchmark_group_id) return;
    if (benchmarkOptions.length === 0) return;
    if (benchmarkOptions.some((item) => item.value === form.benchmark_group_id)) return;
    setField('benchmark_group_id', '');
  }, [benchmarkOptions, form.benchmark_group_id, businessTypeId, selectedType]);

  useEffect(() => {
    if (!selected?.id || !runExecutorAccountId) {
      setRunReadiness(null);
      return;
    }
    void getTaskTemplateRunReadiness(role, selected.id, runExecutorAccountId, userId)
      .then(setRunReadiness)
      .catch(() => setRunReadiness(null));
  }, [selected?.id, runExecutorAccountId, role, userId]);

  async function saveTemplate() {
    if (!editable) return;
    setError('');
    setToast('');
    try {
      const payload = normalizePayload(selectedType, form);
      const detail = selected
        ? await updateTaskTemplate(role, selectedType, selected.id, payload, userId)
        : await createTaskTemplate(role, selectedType, payload, userId);
      setSelected(detail);
      setIsCreating(false);
      setForm(buildFormFromDetail(detail));
      await reloadTemplates();
      await reloadRunContext(detail.id);
      setToast('模板已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  }

  async function runSelected() {
    if (!selected || !runExecutorAccountId) return;
    setError('');
    setToast('');
    setRunLoading(true);
    try {
      const result = await runTaskTemplate(role, selected.id, runExecutorAccountId, userId);
      taskRunRefresh?.trackTaskRun(result.task_run_id);
      setToast(`已创建 ${result.jobs_created} 个 Job，等待 Agent 执行`);
      const detail = await getTaskRun(role, result.task_run_id, userId);
      setActiveRun(detail);
    } catch (err) {
      setError(readableRunError(err));
      const apiError = err as ApiError;
      const readinessDetail = extractReadiness(apiError.detail);
      if (readinessDetail) setRunReadiness(readinessDetail);
      setToast('运行请求失败，请查看原因');
    } finally {
      setRunLoading(false);
    }
  }

  async function createSchedule() {
    if (!selected || !scheduleForm.executor_account_id) return;
    setError('');
    try {
      await createTaskSchedule(role, { ...scheduleForm, task_template_id: selected.id }, userId);
      setToast('定时调度已创建');
      await reloadSchedules(selected.id);
      setScheduleForm({ ...emptyScheduleForm, executor_account_id: scheduleForm.executor_account_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建定时调度失败');
    }
  }

  async function reloadRunContext(templateId: string) {
    try {
      setReadiness(await getTaskTemplateReadiness(role, templateId, userId));
    } catch {
      setReadiness(null);
    }
  }

  useEffect(() => {
    if (!activeRun || ['success', 'partial_success', 'failed'].includes(activeRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getTaskRun(role, activeRun.id, userId);
        setActiveRun(next);
      } catch (err) {
        setError(err instanceof Error ? err.message : '运行状态刷新失败');
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeRun?.id, activeRun?.status, role, userId, selected?.id]);

  useTaskRunRefreshEffect(async () => {
    if (!activeRun) return;
    try {
      const next = await getTaskRun(role, activeRun.id, userId);
      setActiveRun(next);
      if (['success', 'partial_success'].includes(next.status)) {
        setToast('采集任务已完成');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行状态刷新失败');
    }
  }, [activeRun?.id, role, userId]);

  const canRunNow = Boolean(selected && runExecutorAccountId && runReadiness?.ready);

  return (
    <section className="page-grid tasks-grid">
      <aside className="filter-panel tasks-filter-panel">
        <div className="filter-actions">
          <button type="button" onClick={startNewTemplate} disabled={!canCreateTaskTemplate(role)}>
            <Plus size={14} />
            新建模板
          </button>
        </div>
        <div className="tasks-type-filter-field">
          <label htmlFor="task-template-type-filter">类型</label>
          <select
            id="task-template-type-filter"
            data-testid="task-type-filters"
            aria-label="任务模板类型"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value as TaskTypeFilter)}
          >
            <option value="all">全部类型 ({templateCountByType.all ?? 0})</option>
            {TASK_TEMPLATE_TYPES.map((type) => (
              <option key={type} value={type}>
                {TASK_TYPE_META[type].title} ({templateCountByType[type] ?? 0})
              </option>
            ))}
          </select>
        </div>
        <div className="scheduler-note">
          模板按业务类型共享；执行账号在手动运行或定时调度时选择。
        </div>
      </aside>
      <section className="list-panel">
        <div className="section-head">
          <div>
            <h1>任务模板</h1>
            <span>{listPanelSubtitle}</span>
          </div>
          <button className="secondary" onClick={reloadTemplates}><RefreshCw size={14} />刷新</button>
        </div>
        {toast && <div className="toast">{toast}</div>}
        {error && <ErrorState text={error} />}
        {loading ? (
          <LoadingState text="任务模板加载中" />
        ) : templates.length === 0 ? (
          <EmptyState text="暂无任务模板" />
        ) : filteredTemplates.length === 0 ? (
          <EmptyState text="当前筛选下暂无任务模板" />
        ) : (
          <div className="data-table">
            <div className="table-row table-head task-head">
              <span>名称</span>
              <span>类型</span>
              <span>业务类型</span>
              <span>创建者</span>
              <span>状态</span>
              <span>关键参数</span>
              <span>操作</span>
            </div>
            {filteredTemplates.map((template) => (
              <div
                key={template.id}
                className={`table-row task-row ${selected?.id === template.id ? 'selected' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => void openTemplate(template.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    void openTemplate(template.id);
                  }
                }}
              >
                <span className="strong task-col-name">{template.name}</span>
                <span className="task-col-type">{formatTemplateTypeLabel(template.template_type)}</span>
                <span className="task-col-biz">{template.business_account_type_name || '-'}</span>
                <span className="task-col-owner">{template.created_by_display_name || '系统'}</span>
                <span className={`task-col-status ${template.enabled ? 'is-on' : 'is-off'}`}>{template.enabled ? '启用' : '停用'}</span>
                <span className="task-col-keys">{formatTemplateKeyFields(template.key_fields)}</span>
                <button
                  type="button"
                  className="icon-button danger task-col-action"
                  title="删除任务模板"
                  disabled={!canDeleteTemplate(role, template, userId)}
                  onClick={(event) => {
                    event.stopPropagation();
                    void removeTemplate(template);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
      <aside className="detail-panel">
        <div className="panel-title">
          {selected ? (editable ? '编辑模板' : '查看模板') : isCreating ? '新建模板' : '模板详情'}
        </div>
        {!detailOpen ? (
          <EmptyState text="请选择任务模板，或点击左侧「新建模板」" />
        ) : (
        <div className="form-stack" data-testid="dynamic-task-form">
          <div className="detail-section">
            <b>{selectedTypeMeta.title}</b>
            <span className="muted-hint">{selectedTypeMeta.description}</span>
          </div>
          <label htmlFor="task-template-type">模板类型</label>
          <select id="task-template-type" value={selectedType} onChange={(event) => changeFormType(event.target.value as TaskTemplateType)} disabled={!!selected}>
            {options?.task_template_types.map((item) => (
              <option key={item.value} value={item.value}>
                {TASK_TYPE_META[item.value as TaskTemplateType]?.title || item.label}
              </option>
            ))}
          </select>
          <ResourceSelect
            label="业务类型"
            testId="business-type-select"
            value={form.business_account_type_id}
            options={businessTypeOptions}
            onChange={(value) => {
              setField('business_account_type_id', value);
              setField('rule_set_id', '');
              setField('benchmark_group_id', '');
            }}
            disabled={!editable}
          />
          <label>名称</label>
          <input value={form.name} onChange={(event) => setField('name', event.target.value)} disabled={!editable} />
          <label className="check-line"><input type="checkbox" checked={form.enabled} onChange={(event) => setField('enabled', event.target.checked)} disabled={!editable} />启用</label>
          {selectedType === 'recommendation_feed_task' && (
            <>
              <label>Feed Type</label>
              <select value={form.feed_type || ''} onChange={(event) => setField('feed_type', event.target.value)} disabled={!editable}>
                {options?.feed_types.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <label>目标数量</label>
              <input type="number" value={form.target_count || 50} onChange={(event) => setField('target_count', Number(event.target.value))} disabled={!editable} />
              <label>刷新轮数</label>
              <input type="number" value={form.refresh_rounds || 2} onChange={(event) => setField('refresh_rounds', Number(event.target.value))} disabled={!editable} />
              <label>每轮滚动目标</label>
              <input type="number" value={form.per_round_scroll_target || 50} onChange={(event) => setField('per_round_scroll_target', Number(event.target.value))} disabled={!editable} />
            </>
          )}
          {selectedType === 'creator_monitor_task' && (
            <>
              <ResourceSelect label="对标组" testId="benchmark-group-select" value={form.benchmark_group_id} options={benchmarkOptions} onChange={(value) => setField('benchmark_group_id', value)} disabled={!editable} />
              {businessTypeId && !form.benchmark_group_id && benchmarkOptions.length === 0 && (
                <div className="inline-error">当前业务类型尚未绑定对标账号组，请先到对标账号组管理中绑定。</div>
              )}
              <label className="check-line"><input type="checkbox" checked={form.auto_detail_fetch !== false} onChange={(event) => setField('auto_detail_fetch', event.target.checked)} disabled={!editable} />自动补详情</label>
            </>
          )}
          {selectedType === 'keyword_search_task' && (
            <>
              <label>平台</label>
              <select value={form.platform || 'xhs'} onChange={(event) => setField('platform', event.target.value)} disabled={!editable}>
                {options?.platforms.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <label>关键词</label>
              <input value={(form.keywords || []).join(',')} onChange={(event) => setField('keywords', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))} disabled={!editable} />
              <label>最大采样</label>
              <input type="number" value={form.max_items || 50} onChange={(event) => setField('max_items', Number(event.target.value))} disabled={!editable} />
            </>
          )}
          <ResourceSelect label="入库规则" testId="rule-set-select" value={form.rule_set_id} options={ruleSetOptions} onChange={(value) => setField('rule_set_id', value)} disabled={!editable} />
          {businessTypeId && !form.rule_set_id && ruleSetOptions.length === 0 && (
            <div className="inline-error">当前业务类型尚未绑定入库规则，请先到规则管理详情中绑定。</div>
          )}
          <ResourceSelect label="行为策略" testId="behavior-profile-select" value={form.behavior_profile_id} options={behaviorOptions} onChange={(value) => setField('behavior_profile_id', value)} disabled={!editable} />
          <ResourceSelect label="网络出口策略" testId="network-profile-select" value={form.network_egress_profile_id} options={networkOptions} onChange={(value) => setField('network_egress_profile_id', value)} disabled={!editable} />
          <ResourceSelect label="风险策略" testId="risk-policy-select" value={form.risk_policy_id} options={riskOptions} onChange={(value) => setField('risk_policy_id', value)} disabled={!editable} />
          {editable && (
            <div className="action-strip">
              <button onClick={saveTemplate}><Save size={14} />保存</button>
            </div>
          )}
          {selected && readiness && <ReadinessCard readiness={readiness} title={readiness.ready ? '模板配置就绪' : '模板配置未就绪'} />}

          {selected && (
            <div className="detail-section" data-testid="run-panel">
              <b>立即运行</b>
              <ResourceSelect
                label="执行账号"
                testId="executor-account-select"
                value={runExecutorAccountId}
                options={runAccountOptions}
                onChange={setRunExecutorAccountId}
              />
              {runReadiness && <ReadinessCard readiness={runReadiness} title={runReadiness.ready ? '可立即运行' : '当前不可运行'} />}
              <div className="action-strip">
                <button onClick={runSelected} disabled={!canRunNow || runLoading}><Play size={14} />{runLoading ? '运行中' : '立即运行'}</button>
              </div>
            </div>
          )}

          {selected && schedulable && (
            <div className="detail-section" data-testid="schedule-panel">
              <b>定时调度</b>
              {schedules.length > 0 && (
                <div className="mini-list">
                  {schedules.map((item) => (
                    <div key={item.id} className="mini-row passive">
                      <span>{item.schedule_type}</span>
                      <span>{item.enabled ? '启用' : '停用'}</span>
                      <span>{item.executor_account_id}</span>
                    </div>
                  ))}
                </div>
              )}
              <label>调度类型</label>
              <select value={scheduleForm.schedule_type} onChange={(event) => setScheduleForm((current) => ({ ...current, schedule_type: event.target.value }))}>
                <option value="interval_seconds">interval_seconds</option>
                <option value="manual">manual</option>
              </select>
              <label>间隔秒数</label>
              <input type="number" value={scheduleForm.interval_seconds || 3600} onChange={(event) => setScheduleForm((current) => ({ ...current, interval_seconds: Number(event.target.value) }))} />
              <ResourceSelect
                label="执行账号"
                testId="schedule-executor-select"
                value={scheduleForm.executor_account_id}
                options={runAccountOptions}
                onChange={(value) => setScheduleForm((current) => ({ ...current, executor_account_id: value }))}
              />
              <label className="check-line">
                <input type="checkbox" checked={scheduleForm.enabled} onChange={(event) => setScheduleForm((current) => ({ ...current, enabled: event.target.checked }))} />
                启用
              </label>
              <button type="button" className="secondary" onClick={createSchedule}>添加定时调度</button>
            </div>
          )}

          {activeRun && <TaskRunPanel run={activeRun} role={role} onOpenOperations={onOpenOperations} />}
        </div>
        )}
      </aside>
    </section>
  );
}

function normalizePayload(type: TaskTemplateType, form: TaskFormData): TaskFormData {
  const base = clean({
    name: form.name,
    business_account_type_id: form.business_account_type_id,
    enabled: form.enabled,
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

function ReadinessCard({ readiness, title }: { readiness: TaskTemplateReadiness; title: string }) {
  return (
    <div className={`run-result ${readiness.ready ? 'ready' : 'blocked'}`} data-testid="readiness-card">
      <b>{title}</b>
      {readiness.checks.map((check) => (
        <div key={check.key} className={check.ok ? 'check-ok' : 'check-bad'}>{check.ok ? '通过' : '阻塞'} · {check.message}</div>
      ))}
    </div>
  );
}

function TaskRunPanel({ run, role, onOpenOperations }: { run: TaskRun; role: Role; onOpenOperations?: (taskRunId?: string) => void }) {
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
      {queue && queue.pending_jobs_ahead > 5 ? (
        <div className="queue-hint">
          {role === 'operator' ? '等待较久可前往「我的运行」查看进度' : '等待较久可前往运行中心查看队列'}
        </div>
      ) : null}
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
