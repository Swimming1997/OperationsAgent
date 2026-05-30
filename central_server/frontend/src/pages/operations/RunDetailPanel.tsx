import type { OpsJobItem, OpsTaskRunDetail, OpsTaskRunItem } from '../../api/operations';
import { EmptyState } from '../../components/Status';
import {
  formatDateTime,
  formatRunJobStats,
  jobTimeoutLabel,
  labelJobType,
  labelStatus,
  labelTrigger,
} from '../../utils/operationsLabels';
import { isRunNeedsAttention } from '../../utils/operationsRunBuckets';

type Props = {
  run: OpsTaskRunDetail | null;
  jobs: OpsJobItem[];
  canWrite: boolean;
  onCancelPending: (id: string) => void;
  onRetry: (id: string) => void;
  emptyText?: string;
};

export function RunDetailPanel({
  run,
  jobs,
  canWrite,
  onCancelPending,
  onRetry,
  emptyText = '请在列表中选择一条运行记录',
}: Props) {
  if (!run) return <EmptyState text={emptyText} />;
  const resultMessage = extractRunMessage(run.result_summary);
  const conclusion = buildRunConclusion(run, jobs);
  const recommendation = buildRunRecommendation(run, jobs);
  const attention = isRunNeedsAttention(run, jobs);
  return (
    <div className="detail-body" data-testid="run-detail-panel">
      <h3 className="panel-title">运行详情</h3>
      <section className={`ops-diagnosis ${attention || run.status === 'failed' ? 'needs-action' : ''}`}>
        <b>任务结论</b>
        <p>{conclusion}</p>
        <b>建议操作</b>
        <p>{recommendation}</p>
      </section>
      <dl className="detail-dl">
        <div><dt>任务名称</dt><dd>{run.task_template_name || '未命名任务'}</dd></div>
        <div><dt>执行账号</dt><dd>{run.executor_account_name || '—'}</dd></div>
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
          <button type="button" onClick={() => onCancelPending(run.id)}>取消待执行项</button>
          <button type="button" onClick={() => onRetry(run.id)}>重试失败项</button>
        </div>
      ) : null}
      <section className="ops-step-list">
        <b>采集步骤</b>
        {jobs.length === 0 ? <span className="muted">暂无采集步骤明细</span> : jobs.map((job) => (
          <button type="button" key={job.id} className="mini-row passive ops-step-row">
            <span>{labelJobType(job.job_type)}</span>
            <span>{labelStatus(job.status)}</span>
            <span>{job.claimed_by_agent_name || '未分配 Agent'}</span>
            <span>{jobTimeoutLabel(job)}</span>
          </button>
        ))}
      </section>
      <TechnicalDetails data={run} testId="run-tech-details" />
    </div>
  );
}

export function getRunOverviewText(run: OpsTaskRunItem, jobs: OpsJobItem[]): string {
  const issue = getRunIssueText(run, jobs);
  if (issue) return issue.replace(/^异常：|^提示：/, '');
  if (run.status === 'success') return `${run.jobs_success} 个采集步骤已完成`;
  if (run.status === 'running') return `${run.jobs_running} 个执行中，${run.jobs_pending} 个等待`;
  if (run.status === 'queued' || run.status === 'materialized') return `${run.jobs_pending} 个采集步骤等待执行`;
  return formatRunJobStats(run.jobs_pending, run.jobs_running, run.jobs_success, run.jobs_failed);
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

export function getRunIssueText(run: OpsTaskRunItem, jobs: OpsJobItem[]): string {
  if (jobs.some((job) => job.is_stale_running || job.is_stale_claimed)) {
    return '异常：采集步骤执行超时，可能需要释放后重试';
  }
  const failed = jobs.find((job) => job.status === 'failed');
  if (failed?.last_error_message) return `异常：${failed.last_error_message}`;
  if (run.status === 'failed') return '异常：任务执行失败，建议查看右侧详情';
  if (run.status === 'partial_success') return '提示：任务部分完成，可重试失败步骤';
  return '';
}

function buildRunConclusion(run: OpsTaskRunDetail, jobs: OpsJobItem[]): string {
  if (isRunNeedsAttention(run, jobs)) return '任务卡住，存在执行超时的采集步骤。';
  if (run.status === 'success') return `任务已完成，${run.jobs_success} 个采集步骤执行成功。`;
  if (run.status === 'failed') return `任务执行失败，${run.jobs_failed} 个采集步骤失败。`;
  if (run.status === 'partial_success') return `任务部分完成，${run.jobs_success} 个成功，${run.jobs_failed} 个失败。`;
  if (run.status === 'running') return `任务正在执行，${run.jobs_running} 个采集步骤仍在运行。`;
  if (run.status === 'queued' || run.status === 'materialized') return `任务等待执行，${run.jobs_pending} 个采集步骤尚未开始。`;
  return `当前状态：${labelStatus(run.status)}。`;
}

function buildRunRecommendation(run: OpsTaskRunDetail, jobs: OpsJobItem[]): string {
  const stale = jobs.find((job) => job.is_stale_running || job.is_stale_claimed);
  if (stale) return '建议稍后重试失败步骤；若仍无进展请联系主管检查 Agent。';
  const failed = jobs.find((job) => job.status === 'failed');
  if (failed?.last_error_message) return `建议根据错误原因处理后重试：${failed.last_error_message}`;
  if (run.status === 'failed') return '建议检查账号与 Agent 状态后重试失败步骤。';
  if (run.status === 'partial_success') return '可先查看情报中心结果，再决定是否重试失败步骤。';
  if (run.status === 'success') return '无需处理，可前往情报中心查看采集结果。';
  if (run.status === 'queued' || run.status === 'materialized') return '若长时间等待，请确认本机 Agent 在线且账号可用。';
  return '继续观察即可。';
}
