export function formatNumber(value: number | null | undefined): string {
  const number = Number(value || 0);
  if (number >= 10000) return `${(number / 10000).toFixed(number >= 100000 ? 0 : 1)}万`;
  return String(number);
}

export function platformLabel(platform: string | null | undefined): string {
  return platform === 'douyin' ? '抖音' : '小红书';
}

export function mediaUrl(url: string | null | undefined): string {
  return url ? `/api/local/media?url=${encodeURIComponent(url)}` : '';
}

export function statusLabel(status: string): string {
  return (
    {
      queued: '等待中',
      active: '定时中',
      running: '采集中',
      success: '完成',
      failed: '失败',
      paused: '已暂停',
    } as Record<string, string>
  )[status] || status;
}

export function processingStatusLabel(status: string | null | undefined): string {
  return (
    { pending: '待处理', discarded: '已废弃', material: '素材库' } as Record<string, string>
  )[status || 'pending'] || '待处理';
}

export function authStatusLabel(status: string | null | undefined): string {
  return (
    {
      not_logged_in: '未登录',
      login_pending: '登录中',
      active: '已登录',
      error: '登录失败',
      expired: '已过期',
    } as Record<string, string>
  )[status || ''] || String(status || '未知');
}
