import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  cancelTaskRunPending,
  getOpsTaskRun,
  listOpsTaskRuns,
  retryTaskRun,
  type BulkOperationResult,
  type OpsTaskRunDetail,
  type OpsTaskRunItem,
} from '../api/operations';
import { listAccounts } from '../api/resources';
import { useAuth } from '../auth/AuthContext';
import { ListPaginationBar } from '../components/ListPaginationBar';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import { useTaskRunRefreshEffect } from '../context/TaskRunRefreshContext';
import type { PlatformAccount, Role } from '../types/api';
import { getTaskRunDisplayName, labelStatus, labelTrigger } from '../utils/operationsLabels';
import { RUN_BUCKET_FILTER_OPTIONS } from '../utils/operationsRunBuckets';
import { myRunsCreatedAfterIso, sortMyRuns } from '../utils/myRunsSort';
import { getRunOverviewText, RunDetailPanel } from './operations/RunDetailPanel';

type Props = {
  role: Role;
  userId: string;
  initialTaskRunId?: string;
};

type ConfirmAction = {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => Promise<BulkOperationResult>;
};

export function MyRunsPage({ role, userId, initialTaskRunId }: Props) {
  const auth = useAuth();
  const [taskRuns, setTaskRuns] = useState<OpsTaskRunItem[]>([]);
  const [taskRunsTotal, setTaskRunsTotal] = useState(0);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialTaskRunId || null);
  const [selectedRun, setSelectedRun] = useState<OpsTaskRunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [confirm, setConfirm] = useState<ConfirmAction | null>(null);
  const [runStatus, setRunStatus] = useState('');
  const [executorAccountId, setExecutorAccountId] = useState('');
  const [runSearch, setRunSearch] = useState('');
  const [runPage, setRunPage] = useState(1);
  const runPageSize = 30;
  const runTotalPages = Math.max(1, Math.ceil(taskRunsTotal / runPageSize));
  const createdAfter = useMemo(() => myRunsCreatedAfterIso(7), []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await listOpsTaskRuns(
        role,
        {
          page: runPage,
          page_size: runPageSize,
          status_group: runStatus || undefined,
          executor_account_id: executorAccountId || undefined,
          created_after: createdAfter,
        },
        userId,
      );
      setTaskRuns(response.items);
      setTaskRunsTotal(response.total);
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 403) {
        setError('当前账号未绑定员工档案，请联系主管处理。');
      } else {
        setError(err instanceof Error ? err.message : '加载失败');
      }
    } finally {
      setLoading(false);
    }
  }, [role, userId, runStatus, executorAccountId, runPage, createdAfter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    setRunPage(1);
  }, [runStatus, executorAccountId, runSearch]);

  useEffect(() => {
    listAccounts(role, userId)
      .then(setAccounts)
      .catch(() => setAccounts([]));
  }, [role, userId]);

  const refreshSelectedRun = useCallback(async () => {
    if (!selectedRunId) return;
    try {
      setSelectedRun(await getOpsTaskRun(role, selectedRunId, userId));
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(status === 404 ? '无法查看该运行记录，可能不属于你的执行账号。' : err instanceof Error ? err.message : '运行详情刷新失败');
      setSelectedRun(null);
    }
  }, [role, selectedRunId, userId]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    void refreshSelectedRun();
  }, [selectedRunId, refreshSelectedRun]);

  useEffect(() => {
    if (initialTaskRunId) setSelectedRunId(initialTaskRunId);
  }, [initialTaskRunId]);

  useTaskRunRefreshEffect(() => {
    void reload();
    void refreshSelectedRun();
    setToast('任务已完成，列表已更新');
  }, [reload, refreshSelectedRun]);

  const selectedRunIsActive = Boolean(
    selectedRun
      && (selectedRun.has_active_jobs || ['queued', 'running', 'materialized'].includes(selectedRun.status)),
  );

  useEffect(() => {
    if (!selectedRunIsActive) return;
    const timer = window.setInterval(() => {
      void reload();
      void refreshSelectedRun();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selectedRunIsActive, selectedRunId, reload, refreshSelectedRun]);

  const filteredTaskRuns = useMemo(() => {
    const query = runSearch.trim().toLowerCase();
    const matched = taskRuns.filter((run) => {
      if (!query) return true;
      const haystack = [
        run.task_template_name || '',
        run.executor_account_name || '',
        run.id,
      ].join(' ').toLowerCase();
      return haystack.includes(query);
    });
    return sortMyRuns(matched);
  }, [taskRuns, runSearch]);

  useEffect(() => {
    if (filteredTaskRuns.length === 0) {
      if (!initialTaskRunId) setSelectedRunId(null);
      return;
    }
    if (selectedRunId && (filteredTaskRuns.some((run) => run.id === selectedRunId) || selectedRunId === initialTaskRunId)) {
      return;
    }
    if (!selectedRunId) setSelectedRunId(filteredTaskRuns[0].id);
  }, [filteredTaskRuns, initialTaskRunId, selectedRunId]);

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

  if (role !== 'operator') {
    return <ErrorState text="当前页面仅运营员工可访问。" />;
  }

  if (!auth.employeeId && auth.phase === 'authenticated') {
    return (
      <div data-testid="my-runs-no-employee">
        <ErrorState text="当前账号未绑定员工档案，请联系主管绑定后再查看运行记录。" />
      </div>
    );
  }

  return (
    <section className="page-grid operations-grid my-runs-grid" data-testid="my-runs-page">
      <header className="section-head operations-head">
        <div>
          <h1>我的运行</h1>
          <p className="ops-intro">查看你名下执行账号的任务运行状态，处理失败或进行中的问题。</p>
        </div>
        {error ? <span className="inline-error">{error}</span> : null}
        {toast ? <span className="feedback" data-testid="my-runs-toast">{toast}</span> : null}
      </header>

      {loading && taskRuns.length === 0 ? <LoadingState text="加载运行记录中" /> : null}

      <div className="operations-panels">
        <aside className="filter-panel ops-filter-panel" data-testid="my-runs-filter-panel">
          <h2 className="ops-section-title">筛选</h2>
          <div className="filter-grid">
            <label>状态</label>
            <select value={runStatus} onChange={(event) => setRunStatus(event.target.value)} aria-label="运行状态筛选">
              {RUN_BUCKET_FILTER_OPTIONS.map((item) => (
                <option key={item.value || 'all'} value={item.value}>{item.label}</option>
              ))}
            </select>
            <label>执行账号</label>
            <select
              value={executorAccountId}
              onChange={(event) => setExecutorAccountId(event.target.value)}
              aria-label="执行账号筛选"
            >
              <option value="">全部账号</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.display_name}</option>
              ))}
            </select>
            <label>搜索</label>
            <input value={runSearch} onChange={(event) => setRunSearch(event.target.value)} placeholder="任务名、账号、编号" />
          </div>
          <p className="muted my-runs-range-hint">默认显示最近 7 天</p>
        </aside>

        <section className="list-panel ops-run-list-panel" data-testid="my-runs-list">
          <div className="ops-list-head">
            <h2 className="ops-section-title">运行记录</h2>
            <span className="muted">共 {taskRunsTotal} 条 · 第 {runPage}/{runTotalPages} 页</span>
          </div>
          {filteredTaskRuns.length === 0 ? (
            <EmptyState text="暂无符合条件的运行记录" />
          ) : (
            <div className="ops-run-list">
              <div className="ops-run-list-header" aria-hidden>
                <span>任务</span>
                <span>概览</span>
                <span>标签</span>
                <span>状态</span>
              </div>
              {filteredTaskRuns.map((run) => {
                const attention = run.has_stuck_jobs;
                return (
                  <button
                    type="button"
                    key={run.id}
                    className={`ops-run-row ${selectedRunId === run.id ? 'selected' : ''}`}
                    onClick={() => setSelectedRunId(run.id)}
                  >
                    <b>{getTaskRunDisplayName(run)}</b>
                    <span className="ops-run-overview">{getRunOverviewText(run, [])}</span>
                    <span className="ops-run-tags">
                      <span className="tag muted-tag">{run.executor_account_name || '未记录账号'}</span>
                      <span className="tag muted-tag">{labelTrigger(run.trigger_type)}</span>
                    </span>
                    <span className={`tag ${attention ? 'warning-tag' : ''}`}>
                      {attention ? '需关注' : labelStatus(run.status)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          {taskRunsTotal > 0 ? (
            <ListPaginationBar
              testId="my-runs-pagination"
              page={runPage}
              totalPages={runTotalPages}
              disabled={loading}
              onPrev={() => setRunPage((page) => Math.max(1, page - 1))}
              onNext={() => setRunPage((page) => Math.min(runTotalPages, page + 1))}
            />
          ) : null}
        </section>

        <aside className="detail-panel" data-testid="my-runs-detail-panel">
          <RunDetailPanel
            run={selectedRun}
            jobs={selectedRun?.jobs || []}
            canWrite
            emptyText="请在左侧选择一条运行记录"
            onCancelPending={(id) => setConfirm({
              title: '取消待执行项',
              message: '将取消该次运行中所有仍在等待的采集步骤，已开始的不受影响。',
              confirmLabel: '确定取消',
              onConfirm: () => cancelTaskRunPending(role, id, 'my_runs_cancel_pending', userId),
            })}
            onRetry={(id) => setConfirm({
              title: '重试失败项',
              message: '将把本次运行中失败的采集步骤重新加入队列。',
              confirmLabel: '确定重试',
              onConfirm: () => retryTaskRun(role, id, 'my_runs_retry', userId),
            })}
          />
        </aside>
      </div>

      {confirm ? (
        <div className="modal-backdrop" data-testid="my-runs-confirm-dialog">
          <div className="modal-card">
            <b>{confirm.title}</b>
            <p>{confirm.message}</p>
            <div className="modal-actions">
              <button type="button" className="secondary" onClick={() => setConfirm(null)}>返回</button>
              <button type="button" className="danger" onClick={() => void executeConfirm()}>{confirm.confirmLabel}</button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
