/** 情报中心筛选与列表展示用中文标签（value 仍为 API 枚举） */

export const INTELLIGENCE_SOURCE_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'xhs_home_feed', label: '推荐流' },
  { value: 'search', label: '关键词搜索' },
  { value: 'creator_monitor', label: '对标监控' },
] as const;

const PLATFORM_LABELS: Record<string, string> = {
  xhs: '小红书',
  douyin: '抖音',
};

const WORKFLOW_STATUS_LABELS: Record<string, string> = {
  pending_review: '待审核',
  assigned: '已分配',
  selected: '已选中',
  discarded: '已丢弃',
  archived: '已归档',
};

const CANDIDATE_BUCKET_LABELS: Record<string, string> = {
  lead_candidate: '线索候选',
  content_candidate: '内容候选',
  pending_enrichment: '待补全',
  discard: '已过滤',
};

const SOURCE_SURFACE_LABELS: Record<string, string> = {
  xhs_home_feed: '推荐流',
  search: '关键词搜索',
  creator_monitor: '对标监控',
  manual_import: '手动导入',
  douyin_video_home_feed: '抖音视频流',
  douyin_image_home_feed: '抖音图文流',
};

export function labelPlatform(value: string | null | undefined): string {
  if (!value) return '-';
  return PLATFORM_LABELS[value] || value;
}

export function labelWorkflowStatus(value: string | null | undefined): string {
  if (!value) return '-';
  return WORKFLOW_STATUS_LABELS[value] || value;
}

export function labelCandidateBucket(value: string | null | undefined): string {
  if (!value) return '-';
  return CANDIDATE_BUCKET_LABELS[value] || value;
}

export function labelSourceSurface(value: string | null | undefined): string {
  if (!value) return '-';
  return SOURCE_SURFACE_LABELS[value] || value;
}

export function localizeOptionItems(
  items: Array<{ value: string; label: string }>,
  labels: Record<string, string>,
): Array<{ value: string; label: string }> {
  return items.map((item) => ({ value: item.value, label: labels[item.value] || item.label }));
}

const DATA_STATUS_LABELS: Record<string, string> = {
  card_only: '仅卡片',
  detail_ready: '详情就绪',
  comments_ready: '评论就绪',
  detail_failed: '详情失败',
  comments_failed: '评论失败',
};

export function labelDataStatus(value: string | null | undefined): string {
  if (!value) return '-';
  return DATA_STATUS_LABELS[value] || value;
}

export function formatSearchContext(item: {
  search_keyword?: string | null;
  search_sort?: string | null;
  note_type_filter?: string | null;
  publish_time_filter?: string | null;
  best_search_rank?: number | null;
  best_feed_position?: number | null;
}): string {
  const parts: string[] = [];
  if (item.search_keyword) parts.push(item.search_keyword);
  if (item.search_sort) parts.push(`排序:${item.search_sort}`);
  if (item.note_type_filter) parts.push(`类型:${item.note_type_filter}`);
  if (item.publish_time_filter) parts.push(`时间:${item.publish_time_filter}`);
  if (item.best_search_rank != null) parts.push(`搜索#${item.best_search_rank}`);
  if (item.best_feed_position != null) parts.push(`推荐#${item.best_feed_position}`);
  return parts.length ? parts.join(' · ') : '-';
}

export function formatTags(tags: string[] | undefined): string {
  const values = (tags || []).filter(Boolean);
  return values.length ? values.join(' / ') : '-';
}

export function formatDiscoverySourcesSummary(summary: {
  source_surfaces?: Record<string, unknown>;
  search_keywords?: string[];
}): string {
  const surfaces = Object.keys(summary.source_surfaces || {}).map((key) => labelSourceSurface(key));
  const keywords = (summary.search_keywords || []).filter(Boolean);
  const parts = [...new Set([...surfaces, ...keywords])];
  return parts.length ? parts.join(' · ') : '-';
}
