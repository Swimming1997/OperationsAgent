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

const REFERENCE_LIBRARY_TYPE_LABELS: Record<string, string> = {
  lead: '获客库',
  non_lead: '非获客库',
  uncategorized: '待分类',
  benchmark_work: '对标作品',
  lead_case: '获客案例',
  visual_material: '视觉素材',
};

const REFERENCE_LIBRARY_RATING_LABELS: Record<string, string> = {
  poor: '差',
  medium: '中',
  good: '好',
  watching: '待观察',
  S: 'S',
  A: 'A',
  B: 'B',
  C: 'C',
};

const SELECTION_SOURCE_LABELS: Record<string, string> = {
  manual: '我的选中',
  ai: '规则自动',
};

const REFERENCE_LIBRARY_EVENT_LABELS: Record<string, string> = {
  created: '入库',
  updated: '更新',
  manual_selected: '手动选中',
  ai_re_evaluated: '规则重评',
  archived: '移出对标库',
  revoked: '撤回入库',
  moved: '调整分类',
  rated: '调整评级',
  tagged: '更新标签',
  noted: '更新备注',
};

export type ContentStatusBadge = {
  label: string;
  tone: 'neutral' | 'info' | 'lead' | 'success' | 'muted' | 'warn';
};

const REEVALUATE_STATUS_LABELS: Record<string, string> = {
  created: '已自动入库',
  updated: '已按规则更新',
  skipped_manual_locked: '已跳过（人工锁定）',
  skipped_no_candidate_decision: '已跳过（无候选决策）',
  skipped_no_rule_match: '未命中规则',
  skipped_no_rule_profile: '已跳过（无规则配置）',
  skipped_duplicate_evaluation: '已跳过（同版本已评估）',
  failed_not_found: '失败（内容不存在）',
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

export function labelReferenceLibraryType(value: string | null | undefined): string {
  if (!value) return '-';
  return REFERENCE_LIBRARY_TYPE_LABELS[value] || value;
}

export function labelReferenceLibraryRating(value: string | null | undefined): string {
  if (!value) return '-';
  return REFERENCE_LIBRARY_RATING_LABELS[value] || value;
}

export function labelSelectionSource(value: string | null | undefined): string {
  if (!value) return '-';
  return SELECTION_SOURCE_LABELS[value] || value;
}

export function labelReevaluateStatus(value: string | null | undefined): string {
  if (!value) return '-';
  return REEVALUATE_STATUS_LABELS[value] || value;
}

export function labelReferenceLibraryEventType(value: string | null | undefined): string {
  if (!value) return '-';
  return REFERENCE_LIBRARY_EVENT_LABELS[value] || value;
}

/** 情报入库弹窗等与作品库一致的库类型选项 */
export const REFERENCE_LIBRARY_TYPE_FORM_OPTIONS = [
  { value: 'lead', label: '获客库' },
  { value: 'non_lead', label: '非获客库' },
  { value: 'uncategorized', label: '待分类' },
] as const;

export const REFERENCE_LIBRARY_RATING_FORM_OPTIONS = [
  { value: 'watching', label: '待观察' },
  { value: 'poor', label: '差' },
  { value: 'medium', label: '中' },
  { value: 'good', label: '好' },
] as const;

export function isReferenceManualLocked(metadata: Record<string, unknown> | null | undefined): boolean {
  return Boolean(metadata?.selection_locked_by_manual);
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

/** @deprecated 对外展示请用 formatDiscoveryPosition */
export function formatSearchContext(item: {
  search_keyword?: string | null;
  search_sort?: string | null;
  note_type_filter?: string | null;
  publish_time_filter?: string | null;
  best_search_rank?: number | null;
  best_feed_position?: number | null;
}): string {
  return formatDiscoveryPosition(item);
}

export function formatDiscoveryPosition(item: {
  search_keyword?: string | null;
  search_sort?: string | null;
  note_type_filter?: string | null;
  publish_time_filter?: string | null;
  best_search_rank?: number | null;
  best_feed_position?: number | null;
  discovery_sources_summary?: {
    source_surfaces?: Record<string, unknown>;
    search_keywords?: string[];
  };
}): string {
  const surfaces = Object.keys(item.discovery_sources_summary?.source_surfaces || {});
  const keyword =
    item.search_keyword ||
    item.discovery_sources_summary?.search_keywords?.[0] ||
    null;
  const filterParts: string[] = [];
  if (item.search_sort) filterParts.push(`排序:${item.search_sort}`);
  if (item.note_type_filter) filterParts.push(`类型:${item.note_type_filter}`);
  if (item.publish_time_filter) filterParts.push(`时间:${item.publish_time_filter}`);

  if (surfaces.includes('search') || item.best_search_rank != null) {
    const rank = item.best_search_rank ?? item.best_feed_position;
    const rankText = rank != null ? `第${rank}名` : '';
    const main = keyword ? `搜索${rankText} · ${keyword}` : `搜索${rankText}`;
    const joined = [main.trim(), ...filterParts].filter(Boolean).join(' · ');
    return joined || '-';
  }
  if (surfaces.includes('creator_monitor')) {
    const pos = item.best_feed_position;
    const main = pos != null ? `对标监控第${pos}条` : '对标监控';
    return [main, ...filterParts].join(' · ') || main;
  }
  if (
    surfaces.some((s) =>
      ['xhs_home_feed', 'douyin_video_home_feed', 'douyin_image_home_feed'].includes(s),
    )
  ) {
    const pos = item.best_feed_position;
    const main = pos != null ? `推荐流第${pos}条` : '推荐流';
    return [main, ...filterParts].join(' · ') || main;
  }
  if (item.best_feed_position != null) {
    return `列表第${item.best_feed_position}条`;
  }
  if (keyword) {
    return [keyword, ...filterParts].join(' · ');
  }
  return filterParts.length ? filterParts.join(' · ') : '-';
}

export function deriveContentStatusBadge(item: {
  data_status?: string | null;
  candidate_bucket?: string | null;
  workflow_status?: string | null;
  in_reference_library?: boolean;
  reference_library_type?: string | null;
  manual_tags?: string[];
}): ContentStatusBadge {
  if (item.workflow_status === 'discarded' || item.workflow_status === 'archived') {
    return { label: '已丢弃', tone: 'muted' };
  }
  if (item.in_reference_library) {
    const typeLabel = labelReferenceLibraryType(item.reference_library_type);
    return { label: `已入库·${typeLabel}`, tone: 'success' };
  }
  if (
    item.workflow_status === 'selected' ||
    (item.manual_tags || []).includes('稍后看')
  ) {
    return { label: '稍后看', tone: 'info' };
  }
  if (item.candidate_bucket === 'lead_candidate') {
    return { label: '线索', tone: 'lead' };
  }
  if (item.data_status === 'card_only') {
    return { label: '信息不全', tone: 'warn' };
  }
  if (item.candidate_bucket === 'discard') {
    return { label: '已过滤', tone: 'muted' };
  }
  return { label: '待看', tone: 'neutral' };
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
