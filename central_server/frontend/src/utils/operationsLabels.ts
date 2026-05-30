/** 运行中心前台文案：技术枚举 → 产品中文 */

export const JOB_TYPE_LABELS: Record<string, string> = {
  feed_collect: '推荐页采集',
  creator_monitor: '对标账号监控',
  search_collect: '关键词搜索',
  detail_fetch: '内容详情补采',
  comment_fetch: '评论补采',
};

export const STATUS_LABELS: Record<string, string> = {
  pending: '等待执行',
  claimed: '已领取',
  running: '执行中',
  success: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
  partial_success: '部分完成',
  queued: '排队中',
  materialized: '已就绪',
};

export const TRIGGER_LABELS: Record<string, string> = {
  manual: '手动触发',
  scheduled: '定时触发',
};

/** 执行项（Job）状态 — 用于顶部「执行项概览」 */
export const JOB_OVERVIEW_STATUS_LABELS: Record<string, string> = {
  pending: '等待执行',
  claimed: '已领取',
  running: '执行中',
  success: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
  partial_success: '部分完成',
};

/** 运行批次（Task Run）状态 — 用于顶部「运行批次概览」 */
export const TASK_RUN_OVERVIEW_STATUS_LABELS: Record<string, string> = {
  materialized: '已就绪',
  queued: '排队中',
  running: '执行中',
  success: '已完成',
  failed: '执行失败',
  partial_success: '部分完成',
};

/** @deprecated 使用 JOB_OVERVIEW_STATUS_LABELS */
export const OVERVIEW_STATUS_LABELS = JOB_OVERVIEW_STATUS_LABELS;

export const OVERVIEW_SPECIAL = {
  stale_running: {
    label: '超时未结束',
    tooltip: '执行项已超过系统允许时长仍未结束，可能占用 Agent，可处理为失败。',
  },
  legacy_pending: {
    label: '历史遗留待执行',
    tooltip: '无运行批次或测试遗留的待执行项，一般可安全取消，不会删除内容与配置。',
  },
  stale_claimed: {
    label: '超时已领取未执行',
    tooltip: '已被 Agent 领取但长时间未开始执行，建议处理为失败或等待自动超时。',
  },
} as const;

export const EVENT_TYPE_LABELS: Record<string, string> = {
  job_created: '创建执行项',
  job_cancelled: '取消执行项',
  job_retried: '重新排队',
  job_claimed: 'Agent 领取',
  job_started: '开始执行',
  job_completed: '执行完成',
  job_failed: '执行失败',
};

export const JOB_TYPE_FILTER_OPTIONS = Object.entries(JOB_TYPE_LABELS).map(([value, label]) => ({ value, label }));

export const JOB_BUCKET_FILTER_OPTIONS = [
  { value: '', label: '全部执行项' },
  { value: 'waiting', label: '等待执行' },
  { value: 'running', label: '执行中' },
  { value: 'finished', label: '已结束' },
];

/** @deprecated 使用 JOB_BUCKET_FILTER_OPTIONS */
export const JOB_STATUS_FILTER_OPTIONS = JOB_BUCKET_FILTER_OPTIONS;

export function labelJobType(jobType: string): string {
  return JOB_TYPE_LABELS[jobType] || jobType;
}

export function labelStatus(status: string): string {
  return STATUS_LABELS[status] || status;
}

export function labelTrigger(triggerType: string): string {
  return TRIGGER_LABELS[triggerType] || triggerType;
}

export function labelJobOverviewStatus(status: string): string {
  return JOB_OVERVIEW_STATUS_LABELS[status] || status;
}

export function labelTaskRunOverviewStatus(status: string): string {
  return TASK_RUN_OVERVIEW_STATUS_LABELS[status] || status;
}

/** @deprecated 使用 labelJobOverviewStatus */
export function labelOverviewStatus(status: string): string {
  return labelJobOverviewStatus(status);
}

export function labelPriority(priority: number): string {
  if (priority <= 20) return '手动触发优先';
  if (priority <= 50) return '定时任务';
  if (priority >= 70) return '补采任务';
  return '普通';
}

export function labelEventType(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] || eventType;
}

export function formatRunJobStats(pending: number, running: number, success: number, failed: number): string {
  const parts = [
    `${pending} 个等待执行`,
    `${running} 个执行中`,
    `${success} 个已完成`,
  ];
  if (failed > 0) parts.push(`${failed} 个执行失败`);
  return parts.join(' / ');
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

export function jobTimeoutLabel(job: { is_stale_running: boolean; is_stale_claimed?: boolean; is_legacy: boolean }): string {
  if (job.is_stale_running || job.is_stale_claimed) return '已超时';
  if (job.is_legacy) return '历史遗留';
  return '正常';
}
