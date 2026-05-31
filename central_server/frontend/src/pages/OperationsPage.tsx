import { AlertTriangle } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  cancelTaskRunPending,
  fetchQueueSummary,
  getOpsTaskRun,
  listOpsJobs,
  listOpsTaskRuns,
  retryTaskRun,
  type BulkOperationResult,
  type JobQueueSummary,
  type OpsJobItem,
  type OpsTaskRunDetail,
  type OpsTaskRunItem,
} from '../api/operations';
import { listEmployees, type OrgEmployee } from '../api/organization';
import { canReevaluateReference } from '../components/ReferenceRuleExplain';
import { ListPaginationBar } from '../components/ListPaginationBar';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { Role } from '../types/api';
import { useTaskRunRefreshEffect } from '../context/TaskRunRefreshContext';
import { CollectionQualityPanel } from './operations/CollectionQualityPanel';
import { getRunOverviewText, RunDetailPanel } from './operations/RunDetailPanel';
import {
  getTaskRunDisplayName,
  JOB_TYPE_FILTER_OPTIONS,
  labelJobType,
  labelStatus,
  labelTrigger,
} from '../utils/operationsLabels';
import {
  RUN_BUCKET_FILTER_OPTIONS,
  isRunNeedsAttention,
  sortTaskRunsForBucket,
} from '../utils/operationsRunBuckets';

type Props = {
  role: Role;
  userId: string;
  initialTaskRunId?: string;
  initialJobId?: string;
  onOpenTasks?: () => void;
};

type ConfirmAction = {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => Promise<BulkOperationResult>;
};

const TRIGGER_FILTER_OPTIONS = [
  { value: '', label: '全部触发方式' },
  { value: 'manual', label: '手动触发' },
  { value: 'scheduled', label: '定时触发' },
];

const ORPHAN_JOB_TOOLTIP = '未关联运行批次的执行项（多为测试或历史脏数据），不会在下方列表出现，需技术排查。';

export function OperationsPage({ role, userId, initialTaskRunId }: Props) {
  const readonly = role === 'operator';
  const canWrite = !readonly;
  const [summary, setSummary] = useState<JobQueueSummary | null>(null);
  const [taskRuns, setTaskRuns] = useState<OpsTaskRunItem[]>([]);
  const [taskRunsTotal, setTaskRunsTotal] = useState(0);
  const [jobs, setJobs] = useState<OpsJobItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialTaskRunId || null);
  const [selectedRun, setSelectedRun] = useState<OpsTaskRunDetail | null>(null);
  const [employees, setEmployees] = useState<OrgEmployee[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [confirm, setConfirm] = useState<ConfirmAction | null>(null);
  const [runStatus, setRunStatus] = useState('');
  const [jobType, setJobType] = useState('');
  const [ownerEmployeeId, setOwnerEmployeeId] = useState('');
  const [triggerType, setTriggerType] = useState('');
  const [runSearch, setRunSearch] = useState('');
  const [runPage, setRunPage] = useState(1);
  const runPageSize = 30;
  const runTotalPages = Math.max(1, Math.ceil(taskRunsTotal / runPageSize));
  const [staleOnly, setStaleOnly] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [nextSummary, nextRuns, nextJobs] = await Promise.all([
        fetchQueueSummary(role, userId),
        listOpsTaskRuns(
          role,
          {
            page: runPage,
            page_size: runPageSize,
            status_group: runStatus || undefined,
            stuck_only: staleOnly || undefined,
            trigger_type: triggerType || undefined,
          },
          userId,
        ),
        listOpsJobs(
          role,
          {
            page: 1,
            page_size: 200,
            job_type: jobType || undefined,
            stale_running_only: staleOnly || undefined,
          },
          userId,
        ),
      ]);
      setSummary(nextSummary);
      setTaskRuns(nextRuns.items);
      setTaskRunsTotal(nextRuns.total);
      setJobs(nextJobs.items);
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(status === 403 ? '当前角色无权限查看运行中心。' : err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [role, userId, runStatus, triggerType, jobType, staleOnly, runPage]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    setRunPage(1);
  }, [runStatus, triggerType, ownerEmployeeId, jobType, runSearch, staleOnly]);

  useEffect(() => {
    listEmployees(role, userId)
      .then(setEmployees)
      .catch(() => setEmployees([]));
  }, [role, userId]);

  const refreshSelectedRun = useCallback(async () => {
    if (!selectedRunId) return;
    try {
      setSelectedRun(await getOpsTaskRun(role, selectedRunId, userId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行详情刷新失败');
    }
  }, [role, selectedRunId, userId]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    void refreshSelectedRun();
  }, [selectedRunId, refreshSelectedRun]);

  useTaskRunRefreshEffect(() => {
    void reload();
    void refreshSelectedRun();
    setToast('采集任务已完成，列表已更新');
  }, [reload, refreshSelectedRun]);

  const selectedRunIsActive = Boolean(
    selectedRun
      && (
        selectedRun.has_active_jobs
        || ['queued', 'running', 'materialized'].includes(selectedRun.status)
      ),
  );

  useEffect(() => {
    if (!selectedRunIsActive) return;
    const timer = window.setInterval(() => {
      void reload();
      void refreshSelectedRun();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selectedRunIsActive, selectedRunId, reload, refreshSelectedRun]);

  const jobsByRunId = useMemo(() => {
    const map = new Map<string, OpsJobItem[]>();
    jobs.forEach((job) => {
      if (!job.task_run_id) return;
      const items = map.get(job.task_run_id) || [];
      items.push(job);
      map.set(job.task_run_id, items);
    });
    return map;
  }, [jobs]);

  const filteredTaskRuns = useMemo(() => {
    const query = runSearch.trim().toLowerCase();
    const matched = taskRuns.filter((run) => {
      const runJobs = jobsByRunId.get(run.id) || [];
      const ownerLabel = getRunOwnerLabel(run).toLowerCase();
      const typeLabel = getRunTypeLabel(runJobs).toLowerCase();
      if (ownerEmployeeId && run.owner_employee_id !== ownerEmployeeId) return false;
      if (jobType && !runJobs.some((job) => job.job_type === jobType)) return false;
      if (query) {
        const haystack = [
          run.task_template_name || '',
          ownerLabel,
          typeLabel,
          run.id,
          run.requested_by_user_id || '',
          isManualFetchRun(run, runJobs) ? '手动补采' : '',
        ].join(' ').toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
    return sortTaskRunsForBucket(matched, runStatus);
  }, [taskRuns, jobsByRunId, runStatus, ownerEmployeeId, jobType, runSearch]);

  useEffect(() => {
    if (filteredTaskRuns.length === 0) {
      setSelectedRunId(null);
      return;
    }
    if (!selectedRunId || !filteredTaskRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(filteredTaskRuns[0].id);
    }
  }, [filteredTaskRuns, selectedRunId]);

  function handleRunStatusFilterChange(value: string) {
    setRunStatus(value);
    if (staleOnly && value && value !== 'needs_action') {
      setStaleOnly(false);
    }
  }

  function handleOverviewStatusClick(status: string) {
    setRunStatus(status);
    if (staleOnly && status !== 'needs_action') {
      setStaleOnly(false);
    }
  }

  function handleStaleOnlyChange(checked: boolean) {
    setStaleOnly(checked);
    if (checked && !runStatus) {
      setRunStatus('needs_action');
    }
  }

  async function executeConfirm() {
    if (!confirm) return;
    try {
      const result = await confirm.onConfirm();
      setToast(result.message);
      setConfirm(null);
      await reload();
      if (selectedRunId) setSelectedRun(await getOpsTaskRun(role, selectedRunId, userId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败');
      setConfirm(null);
    }
  }

  if (role !== 'admin' && role !== 'supervisor' && role !== 'operator') {
    return <ErrorState text="当前开发身份无法访问运行中心。" />;
  }

  return (
    <section className="page-grid operations-grid">
      <header className="section-head operations-head">
        <HeadMain />
        {error ? <span className="inline-error">{error}</span> : null}
        {toast ? <span className="feedback" data-testid="ops-toast">{toast}</span> : null}
        {canReevaluateReference(role) ? <CollectionQualityPanel role={role} userId={userId} /> : null}
      </header>

      {loading && !summary ? <LoadingState text="运行中心加载中" /> : null}

      {summary ? (
        <section className="ops-overview" data-testid="ops-overview">
          <div className="summary-cards ops-summary-cards" data-testid="task-run-summary">
            <OverviewCard label="任务运行记录" count={taskRunsTotal} />
            <OverviewCard
              label="进行中"
              count={summary.task_run_bucket_counts?.active ?? 0}
              onClick={() => handleOverviewStatusClick('active')}
            />
            <OverviewCard
              label="待处理"
              count={summary.task_run_bucket_counts?.needs_action ?? 0}
              hint={summary.stuck_task_run_count > 0 ? `其中 ${summary.stuck_task_run_count} 个卡住` : undefined}
              tooltip="包含执行失败、部分完成或存在卡住采集步骤的任务。"
              onClick={() => handleOverviewStatusClick('needs_action')}
            />
            <OverviewCard
              label="已完成"
              count={summary.task_run_bucket_counts?.done ?? 0}
              onClick={() => handleOverviewStatusClick('done')}
            />
            {summary.orphan_active_job_count > 0 ? (
              <OverviewCard
                label="异常残留任务"
                count={summary.orphan_active_job_count}
                tooltip={ORPHAN_JOB_TOOLTIP}
                variant="warning"
              />
            ) : null}
          </div>
        </section>
      ) : null}

      <div className="operations-panels">
        <aside className="filter-panel ops-filter-panel" data-testid="ops-filter-panel">
          <h2 className="ops-section-title">筛选任务</h2>
          <div className="filter-grid">
            <label>状态</label>
            <select
              value={runStatus}
              onChange={(event) => handleRunStatusFilterChange(event.target.value)}
              aria-label="任务状态筛选"
            >
              {RUN_BUCKET_FILTER_OPTIONS.map((item) => (
                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>负责人</label>
            <select value={ownerEmployeeId} onChange={(event) => setOwnerEmployeeId(event.target.value)} aria-label="负责人筛选">
              <option value="">全部负责人</option>
              {employees.map((employee) => (
                <option key={employee.id} value={employee.id}>{employee.display_name}</option>
              ))}
            </select>
            <label>任务类型</label>
            <select value={jobType} onChange={(event) => setJobType(event.target.value)} aria-label="任务类型筛选">
              <option value="">全部任务类型</option>
              {JOB_TYPE_FILTER_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>触发方式</label>
            <select value={triggerType} onChange={(event) => setTriggerType(event.target.value)} aria-label="触发方式筛选">
              {TRIGGER_FILTER_OPTIONS.map((item) => (
                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>搜索</label>
            <input value={runSearch} onChange={(event) => setRunSearch(event.target.value)} placeholder="任务名、负责人、编号" />
            <span aria-hidden />
            <label className="check-line">
              <input
                type="checkbox"
                checked={staleOnly}
                onChange={(event) => handleStaleOnlyChange(event.target.checked)}
                aria-label="仅看执行超时"
              />
              仅看执行超时
            </label>
          </div>
        </aside>

        <section className="list-panel ops-run-list-panel" data-testid="run-batch-list">
          <div className="ops-list-head">
            <h2 className="ops-section-title">任务运行记录</h2>
            <span className="muted">共 {taskRunsTotal} 条 · 第 {runPage}/{runTotalPages} 页</span>
          </div>
          {filteredTaskRuns.length === 0 ? <EmptyState text="暂无符合条件的任务运行记录" /> : (
            <div className="ops-run-list">
              <div className="ops-run-list-header" aria-hidden>
                <span>任务</span>
                <span>概览</span>
                <span>标签</span>
                <span>状态</span>
              </div>
              {filteredTaskRuns.map((run) => {
                const runJobs = jobsByRunId.get(run.id) || [];
                const attention = isRunNeedsAttention(run, runJobs);
                const manualFetch = isManualFetchRun(run, runJobs);
                return (
                  <button
                    type="button"
                    key={run.id}
                    className={`ops-run-row ${selectedRunId === run.id ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedRunId(run.id);
                    }}
                  >
                    <b>{getTaskRunDisplayName(run, runJobs)}</b>
                    <span className="ops-run-overview">
                      {getRunOverviewText(run, runJobs)}
                    </span>
                    <span className="ops-run-tags">
                      <span className="tag muted-tag">{getRunOwnerLabel(run)}</span>
                      {manualFetch ? <span className="tag muted-tag">手动补采</span> : null}
                      <span className="tag muted-tag">{getRunTypeLabel(runJobs)}</span>
                      <span className="tag muted-tag">{labelTrigger(run.trigger_type)}</span>
                    </span>
                    <span className={`tag ${attention ? 'warning-tag' : ''}`}>{attention ? '卡住需处理' : labelStatus(run.status)}</span>
                  </button>
                );
              })}
            </div>
          )}
          {taskRunsTotal > 0 ? (
            <ListPaginationBar
              testId="ops-pagination"
              page={runPage}
              totalPages={runTotalPages}
              disabled={loading}
              onPrev={() => setRunPage((page) => Math.max(1, page - 1))}
              onNext={() => setRunPage((page) => Math.min(runTotalPages, page + 1))}
            />
          ) : null}
        </section>

        <aside className="detail-panel" data-testid="ops-detail-panel">
          <RunDetailPanel
            run={selectedRun}
            jobs={selectedRun?.jobs || []}
            canWrite={canWrite}
            onCancelPending={(id) => setConfirm({
              title: '取消本批次尚未执行的项',
              message: '将取消该任务运行记录下所有仍处于「等待执行」状态的采集步骤。已开始或已完成的步骤不受影响。',
              confirmLabel: '确定取消',
              onConfirm: () => cancelTaskRunPending(role, id, 'operations_cancel_task_run_pending', userId),
            })}
            onRetry={(id) => setConfirm({
              title: '重试失败采集步骤',
              message: '将把该任务运行记录下所有「执行失败」的采集步骤重新加入队列，不会删除历史记录。',
              confirmLabel: '确定重新排队',
              onConfirm: () => retryTaskRun(role, id, 'operations_retry_task_run', userId),
            })}
          />
        </aside>
      </div>

      {readonly ? <p className="inline-error"><AlertTriangle size={14} /> 当前账号在运行中心仅可查看，无法执行清理操作。</p> : null}

      {confirm ? (
        <div className="modal-backdrop" data-testid="confirm-dialog">
          <div className="modal-card">
            <b>{confirm.title}</b>
            <p>{confirm.message}</p>
            <ConfirmActions confirm={confirm} onDismiss={() => setConfirm(null)} onConfirm={() => void executeConfirm()} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function HeadMain() {
  return (
    <div>
      <h1>运行中心</h1>
      <p className="ops-intro">
        查看每次任务运行的状态、负责人和异常原因。先从中间列表定位任务，再在右侧处理失败或卡住的问题。
      </p>
    </div>
  );
}

function OverviewCard({
  label,
  count,
  hint,
  tooltip,
  onClick,
  variant,
}: {
  label: string;
  count: number;
  hint?: string;
  tooltip?: string;
  onClick?: () => void;
  variant?: 'warning';
}) {
  const body = (
    <>
      <b>{label}</b>
      <span>{count}</span>
      {hint ? <span className="summary-card-hint">{hint}</span> : null}
    </>
  );
  const className = variant === 'warning' ? 'summary-card summary-card-warning' : 'summary-card';
  if (onClick) {
    return (
      <button type="button" className={className} title={tooltip} onClick={onClick}>
        {body}
      </button>
    );
  }
  return (
    <div className={className} title={tooltip} data-testid={variant === 'warning' ? 'ops-orphan-warning-card' : undefined}>
      {body}
    </div>
  );
}

function ConfirmActions({
  confirm,
  onDismiss,
  onConfirm,
}: {
  confirm: ConfirmAction;
  onDismiss: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-actions">
      <button type="button" className="secondary" onClick={onDismiss}>返回</button>
      <button type="button" className="danger" onClick={onConfirm}>{confirm.confirmLabel}</button>
    </div>
  );
}

function getRunOwnerLabel(run: OpsTaskRunItem): string {
  if (run.owner_employee_name) return run.owner_employee_name;
  if (run.requested_by_display_name) return `发起人：${run.requested_by_display_name}`;
  return '未记录负责人';
}

function getRunTypeLabel(jobs: OpsJobItem[]): string {
  const firstJob = jobs[0];
  return firstJob ? labelJobType(firstJob.job_type) : '任务运行';
}

function isManualFetchRun(run: OpsTaskRunItem, jobs: OpsJobItem[]): boolean {
  if (!run.task_template_id) return true;
  return jobs.some((job) => job.payload_json?.manual_enqueue === true);
}
