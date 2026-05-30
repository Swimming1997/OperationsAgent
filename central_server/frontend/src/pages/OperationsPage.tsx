import { AlertTriangle, HelpCircle, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  cancelOpsJob,
  cancelTaskRunPending,
  cleanupLegacyPending,
  failStaleRunningJobs,
  fetchQueueSummary,
  getOpsJob,
  getOpsTaskRun,
  listOpsJobs,
  listOpsTaskRuns,
  retryOpsJob,
  retryTaskRun,
  type BulkOperationResult,
  type JobQueueSummary,
  type OpsJobDetail,
  type OpsJobItem,
  type OpsTaskRunDetail,
  type OpsTaskRunItem,
} from '../api/operations';
import { canReevaluateReference } from '../components/ReferenceRuleExplain';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import type { Role } from '../types/api';
import { CollectionQualityPanel } from './operations/CollectionQualityPanel';
import {
  JOB_STATUS_FILTER_OPTIONS,
  JOB_TYPE_FILTER_OPTIONS,
  OVERVIEW_SPECIAL,
  RUN_STATUS_FILTER_OPTIONS,
  formatDateTime,
  formatRunJobStats,
  jobTimeoutLabel,
  labelEventType,
  labelJobOverviewStatus,
  labelJobType,
  labelPriority,
  labelStatus,
  labelTaskRunOverviewStatus,
  labelTrigger,
} from '../utils/operationsLabels';

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

export function OperationsPage({ role, userId, initialTaskRunId, initialJobId, onOpenTasks }: Props) {
  const readonly = role === 'operator';
  const canWrite = !readonly;
  const [summary, setSummary] = useState<JobQueueSummary | null>(null);
  const [taskRuns, setTaskRuns] = useState<OpsTaskRunItem[]>([]);
  const [jobs, setJobs] = useState<OpsJobItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialTaskRunId || null);
  const [selectedRun, setSelectedRun] = useState<OpsTaskRunDetail | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(initialJobId || null);
  const [selectedJob, setSelectedJob] = useState<OpsJobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [confirm, setConfirm] = useState<ConfirmAction | null>(null);
  const [runStatus, setRunStatus] = useState('');
  const [jobStatus, setJobStatus] = useState('');
  const [jobType, setJobType] = useState('');
  const [taskRunFilter, setTaskRunFilter] = useState(initialTaskRunId || '');
  const [legacyOnly, setLegacyOnly] = useState(false);
  const [staleOnly, setStaleOnly] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [nextSummary, nextRuns, nextJobs] = await Promise.all([
        fetchQueueSummary(role, userId),
        listOpsTaskRuns(role, { page: 1, page_size: 30, status: runStatus || undefined }, userId),
        listOpsJobs(
          role,
          {
            page: 1,
            page_size: 80,
            status: jobStatus || undefined,
            job_type: jobType || undefined,
            task_run_id: taskRunFilter || undefined,
            legacy_only: legacyOnly || undefined,
            stale_running_only: staleOnly || undefined,
          },
          userId,
        ),
      ]);
      setSummary(nextSummary);
      setTaskRuns(nextRuns.items);
      setJobs(nextJobs.items);
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(status === 403 ? '当前角色无权限查看运行中心。' : err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [role, userId, runStatus, jobStatus, jobType, taskRunFilter, legacyOnly, staleOnly]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (initialJobId) setSelectedJobId(initialJobId);
  }, [initialJobId]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    getOpsTaskRun(role, selectedRunId, userId).then(setSelectedRun).catch((err) => setError(err.message));
  }, [selectedRunId, role, userId]);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null);
      return;
    }
    getOpsJob(role, selectedJobId, userId).then(setSelectedJob).catch((err) => setError(err.message));
  }, [selectedJobId, role, userId]);

  const taskRunOverviewCards = useMemo(() => {
    if (!summary) return [];
    const counts = summary.task_run_status_counts || {};
    return Object.entries(counts)
      .filter(([, count]) => count > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([status, count]) => ({ status, count, label: labelTaskRunOverviewStatus(status) }));
  }, [summary]);

  const jobOverviewCards = useMemo(() => {
    if (!summary) return [];
    const counts = summary.job_status_counts || summary.status_counts;
    return Object.entries(counts)
      .filter(([, count]) => count > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([status, count]) => ({ status, count, label: labelJobOverviewStatus(status) }));
  }, [summary]);

  async function executeConfirm() {
    if (!confirm) return;
    try {
      const result = await confirm.onConfirm();
      setToast(result.message);
      setConfirm(null);
      await reload();
      if (selectedRunId) setSelectedRun(await getOpsTaskRun(role, selectedRunId, userId));
      if (selectedJobId) setSelectedJob(await getOpsJob(role, selectedJobId, userId));
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
        <OperationsHelp />
        {error ? <span className="inline-error">{error}</span> : null}
        {toast ? <span className="feedback" data-testid="ops-toast">{toast}</span> : null}
        <HeadActions onRefresh={() => void reload()} onOpenTasks={onOpenTasks} />
      </header>

      {loading && !summary ? <LoadingState text="运行中心加载中" /> : null}

      {summary ? (
        <section className="ops-overview" data-testid="ops-overview">
          <h2 className="ops-section-title">运行批次概览</h2>
          <p className="ops-overview-hint">以下数字为「运行批次」数量（每次任务运行一次），与下方左侧列表口径一致。</p>
          <div className="summary-cards" data-testid="task-run-summary">
            {taskRunOverviewCards.length === 0 ? (
              <OverviewCard label="暂无运行批次记录" count={0} />
            ) : (
              taskRunOverviewCards.map((item) => (
                <OverviewCard key={`run-${item.status}`} label={item.label} count={item.count} />
              ))
            )}
          </div>
          <h2 className="ops-section-title">执行项概览</h2>
          <p className="ops-overview-hint">以下数字为底层「执行项」数量（采集、补采等），与下方执行项列表口径一致；可能与运行批次数量不同。</p>
          <div className="summary-cards" data-testid="queue-summary">
            <OverviewCard label={OVERVIEW_SPECIAL.stale_running.label} count={summary.stale_running_count} tooltip={OVERVIEW_SPECIAL.stale_running.tooltip} />
            <OverviewCard label={OVERVIEW_SPECIAL.legacy_pending.label} count={summary.legacy_pending_count} tooltip={OVERVIEW_SPECIAL.legacy_pending.tooltip} />
            <OverviewCard label={OVERVIEW_SPECIAL.stale_claimed.label} count={summary.stale_claimed_count} tooltip={OVERVIEW_SPECIAL.stale_claimed.tooltip} />
            {jobOverviewCards.map((item) => (
              <OverviewCard key={`job-${item.status}`} label={item.label} count={item.count} />
            ))}
            {summary.orphan_active_job_count > 0 ? (
              <OverviewCard
                label="无运行批次的活跃执行项"
                count={summary.orphan_active_job_count}
                tooltip="这些执行项未关联运行批次（多为测试遗留），左侧运行批次列表不会出现。"
              />
            ) : null}
          </div>
          {canWrite ? (
            <AdminActions summary={summary} role={role} userId={userId} setToast={setToast} setConfirm={setConfirm} />
          ) : null}
        </section>
      ) : null}

      {canReevaluateReference(role) ? <CollectionQualityPanel role={role} userId={userId} /> : null}

      <div className="operations-panels">
        <aside className="list-panel" data-testid="run-batch-list">
          <h2 className="ops-section-title">运行批次</h2>
          <label>运行批次状态</label>
          <select value={runStatus} onChange={(event) => setRunStatus(event.target.value)} aria-label="运行批次状态筛选">
            {RUN_STATUS_FILTER_OPTIONS.map((item) => (
              <option key={item.value || 'all'} value={item.value}>{item.label}</option>
            ))}
          </select>
          {taskRuns.length === 0 ? <EmptyState text="暂无运行批次" /> : taskRuns.map((run) => (
            <button
              type="button"
              key={run.id}
              className={`run-batch-card ${selectedRunId === run.id ? 'selected' : ''}`}
              onClick={() => {
                setSelectedRunId(run.id);
                setTaskRunFilter(run.id);
              }}
            >
              <b>{run.task_template_name || '未命名任务'}</b>
              <span className="tag">{labelStatus(run.status)}</span>
              <span className="run-batch-stats">
                {formatRunJobStats(run.jobs_pending, run.jobs_running, run.jobs_success, run.jobs_failed)}
              </span>
              <span className="muted">{labelTrigger(run.trigger_type)}</span>
            </button>
          ))}
        </aside>

        <section className="list-panel" data-testid="execution-item-list">
          <h2 className="ops-section-title">执行项列表</h2>
          <div className="filter-grid">
            <label>执行项状态</label>
            <select value={jobStatus} onChange={(event) => setJobStatus(event.target.value)} aria-label="执行项状态筛选">
              {JOB_STATUS_FILTER_OPTIONS.map((item) => (
                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>执行项类型</label>
            <select value={jobType} onChange={(event) => setJobType(event.target.value)} aria-label="执行项类型筛选">
              <option value="">全部类型</option>
              {JOB_TYPE_FILTER_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>所属运行批次</label>
            <input value={taskRunFilter} onChange={(event) => setTaskRunFilter(event.target.value)} placeholder="可选，输入批次编号筛选" />
            <label className="check-line">
              <input type="checkbox" checked={legacyOnly} onChange={(event) => setLegacyOnly(event.target.checked)} />
              仅显示历史遗留待执行项
            </label>
            <label className="check-line">
              <input type="checkbox" checked={staleOnly} onChange={(event) => setStaleOnly(event.target.checked)} />
              仅显示超时未结束项
            </label>
          </div>
          {jobs.length === 0 ? <EmptyState text="暂无执行项" /> : (
            <div className="data-table compact ops-job-table">
              <JobTableHead />
              {jobs.map((job) => (
                <button
                  type="button"
                  key={job.id}
                  className={`table-row mini ops-job-row ${selectedJobId === job.id ? 'selected' : ''}`}
                  onClick={() => setSelectedJobId(job.id)}
                >
                  <span>{labelJobType(job.job_type)}</span>
                  <span>{labelStatus(job.status)}</span>
                  <span>{labelPriority(job.priority)}</span>
                  <span>{jobTimeoutLabel(job)}</span>
                  <span>{job.claimed_by_agent_name || '—'}</span>
                  <span>{formatDateTime(job.created_at)}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <aside className="detail-panel" data-testid="ops-detail-panel">
          <RunDetailPanel
            run={selectedRun}
            canWrite={canWrite}
            onCancelPending={(id) => setConfirm({
              title: '取消本批次尚未执行的项',
              message: '将取消该运行批次下所有仍处于「等待执行」状态的执行项。已开始或已完成的项不受影响。',
              confirmLabel: '确定取消待执行项',
              onConfirm: () => cancelTaskRunPending(role, id, 'operations_cancel_task_run_pending', userId),
            })}
            onRetry={(id) => setConfirm({
              title: '重试本批次失败项',
              message: '将把该运行批次下所有「执行失败」的执行项重新加入队列，不会删除历史记录。',
              confirmLabel: '确定重新排队',
              onConfirm: () => retryTaskRun(role, id, 'operations_retry_task_run', userId),
            })}
          />
          <JobDetailPanel
            job={selectedJob}
            runName={selectedRun?.task_template_name}
            canWrite={canWrite}
            onCancel={(id) => setConfirm({
              title: '取消待执行项',
              message: '将取消该执行项，使其不再进入队列。已开始执行的项请使用「处理超时执行项」。',
              confirmLabel: '确定取消该项',
              onConfirm: () => cancelOpsJob(role, id, 'operations_cancel_job', userId),
            })}
            onRetry={(id) => setConfirm({
              title: '重试失败项',
              message: '将把该执行项重新加入队列等待 Agent 执行。',
              confirmLabel: '确定重新排队',
              onConfirm: () => retryOpsJob(role, id, 'operations_retry_job', userId),
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
        查看任务运行状态、执行队列和异常执行项。普通使用优先查看「运行批次」，仅在任务卡住或失败时处理执行项。
      </p>
    </div>
  );
}

function OperationsHelp() {
  return (
    <details className="ops-help" data-testid="ops-help">
      <summary><HelpCircle size={14} /> 如何使用运行中心？</summary>
      <ol>
        <li>先看运行批次，了解每次任务整体是否完成；</li>
        <li>如果任务一直排队，查看是否有其他执行项占用 Agent；</li>
        <li>如果发现超时未结束执行项，可处理为失败；</li>
        <li>如果发现历史遗留待执行项，可取消；</li>
        <li>正常运营中，一般不需要频繁手动清理。</li>
      </ol>
    </details>
  );
}

function HeadActions({ onRefresh, onOpenTasks }: { onRefresh: () => void; onOpenTasks?: () => void }) {
  return (
    <div className="head-actions">
      <button type="button" className="secondary" onClick={onRefresh}><RefreshCw size={14} />刷新</button>
      {onOpenTasks ? <button type="button" className="secondary" onClick={onOpenTasks}>返回任务模板</button> : null}
    </div>
  );
}

function OverviewCard({ label, count, tooltip }: { label: string; count: number; tooltip?: string }) {
  return (
    <div className="summary-card" title={tooltip}>
      <b>{label}</b>
      <span>{count}</span>
    </div>
  );
}

function JobTableHead() {
  return (
    <div className="table-row mini table-head ops-job-row" aria-hidden>
      <span>执行项类型</span>
      <span>当前状态</span>
      <span>优先级</span>
      <span>是否超时</span>
      <span>所属 Agent</span>
      <span>创建时间</span>
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

function AdminActions({
  summary,
  role,
  userId,
  setToast,
  setConfirm,
}: {
  summary: JobQueueSummary;
  role: Role;
  userId: string;
  setToast: (value: string) => void;
  setConfirm: (action: ConfirmAction | null) => void;
}) {
  const staleCount = summary.stale_running_count;
  const legacyCount = summary.legacy_pending_count;
  return (
    <div className="summary-actions" data-testid="admin-actions">
      <button
        type="button"
        onClick={() => setConfirm({
          title: '处理超时执行项',
          message: `将把 ${staleCount} 个超过超时阈值、仍未结束的执行项标记为失败，是否继续？`,
          confirmLabel: '确定处理',
          onConfirm: () => failStaleRunningJobs(role, 'operations_fail_stale_running', userId),
        })}
      >
        处理超时执行项
      </button>
      <button
        type="button"
        onClick={async () => {
          const result = await cleanupLegacyPending(role, { reason: 'preview', dry_run: true }, userId);
          setToast(`预览完成：当前约有 ${result.affected_count} 个历史遗留待执行项（未做任何修改）。`);
        }}
      >
        查看历史遗留待执行项
      </button>
      <button
        type="button"
        className="danger"
        onClick={() => setConfirm({
          title: '取消历史遗留待执行项',
          message: `将取消 ${legacyCount} 个历史遗留待执行项。该操作不会删除内容数据和配置，是否继续？`,
          confirmLabel: '确定取消遗留项',
          onConfirm: () => cleanupLegacyPending(role, { reason: 'operations_cleanup_legacy', dry_run: false }, userId),
        })}
      >
        取消历史遗留待执行项
      </button>
    </div>
  );
}

function RunDetailPanel({
  run,
  canWrite,
  onCancelPending,
  onRetry,
}: {
  run: OpsTaskRunDetail | null;
  canWrite: boolean;
  onCancelPending: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  if (!run) return <EmptyState text="请在左侧选择一次运行批次" />;
  const resultMessage = extractRunMessage(run.result_summary);
  return (
    <div className="detail-body" data-testid="run-detail-panel">
      <h3 className="panel-title">运行批次详情</h3>
      <dl className="detail-dl">
        <div><dt>任务名称</dt><dd>{run.task_template_name || '未命名任务'}</dd></div>
        <div><dt>运行状态</dt><dd>{labelStatus(run.status)}</dd></div>
        <div><dt>触发方式</dt><dd>{labelTrigger(run.trigger_type)}</dd></div>
        <div><dt>执行项统计</dt><dd>{formatRunJobStats(run.jobs_pending, run.jobs_running, run.jobs_success, run.jobs_failed)}</dd></div>
        <div><dt>创建时间</dt><dd>{formatDateTime(run.created_at)}</dd></div>
        <div><dt>完成时间</dt><dd>{formatDateTime(run.finished_at)}</dd></div>
        {resultMessage ? <div className="full-row"><dt>运行结果</dt><dd>{resultMessage}</dd></div> : null}
        {run.queue_context?.message ? <div className="full-row queue-hint"><dt>队列提示</dt><dd>{String(run.queue_context.message)}</dd></div> : null}
      </dl>
      {canWrite ? (
        <div className="action-strip">
          <button type="button" onClick={() => onCancelPending(run.id)}>取消本批次待执行项</button>
          <button type="button" onClick={() => onRetry(run.id)}>重试本批次失败项</button>
        </div>
      ) : null}
      <TechnicalDetails data={run} testId="run-tech-details" />
    </div>
  );
}

function JobDetailPanel({
  job,
  runName,
  canWrite,
  onCancel,
  onRetry,
}: {
  job: OpsJobDetail | null;
  runName?: string | null;
  canWrite: boolean;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  if (!job) return null;
  return (
    <div className="detail-body job-detail" data-testid="job-detail-panel">
      <h3 className="panel-title">执行项详情</h3>
      <dl className="detail-dl">
        <div><dt>执行项类型</dt><dd>{labelJobType(job.job_type)}</dd></div>
        <div><dt>当前状态</dt><dd>{labelStatus(job.status)}</dd></div>
        <div><dt>所属运行批次</dt><dd>{runName || job.task_template_name || '—'}</dd></div>
        <div><dt>优先级</dt><dd>{labelPriority(job.priority)}</dd></div>
        <div><dt>所属 Agent</dt><dd>{job.claimed_by_agent_name || '—'}</dd></div>
        <div><dt>是否超时</dt><dd>{jobTimeoutLabel(job)}</dd></div>
        <div><dt>创建时间</dt><dd>{formatDateTime(job.created_at)}</dd></div>
        <div><dt>开始时间</dt><dd>{formatDateTime(job.started_at)}</dd></div>
        <div><dt>完成时间</dt><dd>{formatDateTime(job.finished_at)}</dd></div>
        {job.last_error_message ? (
          <div className="full-row"><dt>错误原因</dt><dd className="inline-error">{job.last_error_message}</dd></div>
        ) : null}
      </dl>
      {job.events.length > 0 ? (
        <div className="event-summary">
          <b>操作记录</b>
          {job.events.map((event, index) => (
            <span key={`${event.event_type}-${index}`}>{labelEventType(event.event_type)} · {formatDateTime(event.created_at)}</span>
          ))}
        </div>
      ) : null}
      {canWrite && job.status === 'pending' ? (
        <button type="button" onClick={() => onCancel(job.id)}>取消该待执行项</button>
      ) : null}
      {canWrite && job.status === 'failed' ? (
        <button type="button" onClick={() => onRetry(job.id)}>重试该失败项</button>
      ) : null}
      <TechnicalDetails
        data={{ payload: job.payload_json, result: job.result_summary_json, events: job.events, id: job.id }}
        testId="job-tech-details"
      />
    </div>
  );
}

function TechnicalDetails({ data, testId }: { data: unknown; testId?: string }) {
  return (
    <details className="tech-details" data-testid={testId}>
      <summary>查看技术详情</summary>
      <pre className="json-block">{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}

function extractRunMessage(resultSummary: Record<string, unknown>): string {
  for (const key of ['feed_collect', 'creator_monitor', 'keyword_search']) {
    const block = resultSummary[key] as { message?: string } | undefined;
    if (block?.message) return block.message;
  }
  return '';
}
