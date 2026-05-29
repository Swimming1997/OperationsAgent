import { SafeImage } from '../../components/SafeImage';
import { EmptyState, LoadingState } from '../../components/Status';
import type { IntelligenceItem } from '../../types/api';
import {
  deriveContentStatusBadge,
  formatDiscoverySourcesSummary,
  labelDataStatus,
} from '../../utils/intelligenceLabels';
import { formatMetric } from '../../utils/formatMetric';
import { coverSrc } from '../../utils/mediaUrl';

type Props = {
  items: IntelligenceItem[];
  selectedId: string | null;
  selectedIds: string[];
  loading: boolean;
  onSelect: (contentId: string) => void;
  onToggleSelect: (contentId: string) => void;
};

function deriveQuickTags(item: IntelligenceItem) {
  const tags: Array<{ label: string; tone?: string }> = [];
  if (item.candidate_bucket === 'lead_candidate') tags.push({ label: '线索', tone: 'lead' });
  if (item.candidate_bucket === 'content_candidate') tags.push({ label: '内容', tone: 'info' });
  if ((item.like_count || 0) >= 100) tags.push({ label: '高互动', tone: 'success' });
  if (item.data_status === 'comments_ready') tags.push({ label: '评论已采', tone: 'success' });
  if (item.data_status === 'card_only' || item.candidate_bucket === 'pending_enrichment') tags.push({ label: '待补采', tone: 'warn' });
  if (item.in_reference_library) tags.push({ label: '已入库', tone: 'success' });
  if (tags.length === 0 && item.data_status) tags.push({ label: labelDataStatus(item.data_status), tone: 'neutral' });
  return tags.slice(0, 4);
}

export function IntelligenceContentList({
  items,
  selectedId,
  selectedIds,
  loading,
  onSelect,
  onToggleSelect,
}: Props) {
  if (loading) {
    return <LoadingState text="列表加载中" />;
  }
  if (items.length === 0) {
    return <EmptyState text="暂无情报内容" />;
  }

  return (
    <div className="data-table intelligence-content-table">
      <div className="table-row table-head intelligence-content-row" data-testid="intelligence-table-head">
        <span>选择</span>
        <span>内容</span>
        <span>互动</span>
        <span>状态</span>
        <span>来源</span>
      </div>
      {items.map((item) => {
        const badge = deriveContentStatusBadge(item);
        return (
          <button
            key={item.content_id}
            type="button"
            className={`table-row intelligence-content-row ${item.content_id === selectedId ? 'selected' : ''}`}
            onClick={() => onSelect(item.content_id)}
          >
            <span className="select-thumb">
              <input
                type="checkbox"
                checked={selectedIds.includes(item.content_id)}
                onChange={(event) => {
                  event.stopPropagation();
                  onToggleSelect(item.content_id);
                }}
                onClick={(event) => event.stopPropagation()}
              />
              <SafeImage src={coverSrc(item)} className="thumb-image" placeholderClassName="cover-empty" />
            </span>
            <span className="content-title-cell">
              <span className="strong">{item.title || '未命名内容'}</span>
              <span className="muted-line">{item.author_name || '未知作者'}</span>
              <span className="quick-tag-row">
                {deriveQuickTags(item).map((tag) => (
                  <b key={tag.label} className={`tag status-badge status-${tag.tone || 'neutral'}`}>{tag.label}</b>
                ))}
              </span>
            </span>
            <span className="metric-compact">
              {formatMetric(item.like_count)} / {formatMetric(item.comment_count)} / {formatMetric(item.collect_count)}
            </span>
            <span>
              <b className={`tag status-badge status-${badge.tone}`}>{badge.label}</b>
            </span>
            <span className="source-cell">{formatDiscoverySourcesSummary(item.discovery_sources_summary)}</span>
          </button>
        );
      })}
    </div>
  );
}
