import type { ReferenceLibraryReevaluateResult } from '../types/api';
import {
  formatTags,
  isReferenceManualLocked,
  labelReferenceLibraryRating,
  labelReferenceLibraryType,
  labelReevaluateStatus,
  labelSelectionSource,
} from '../utils/intelligenceLabels';

export type ReferenceExplainSnapshot = {
  in_library?: boolean;
  library_type?: string | null;
  rating?: string | null;
  selection_sources?: string[];
  matched_keywords?: string[];
  ai_reason?: string | null;
  selected_reason?: string | null;
  metadata?: Record<string, unknown> | null;
  manual_locked?: boolean;
};

type Props = {
  snapshot: ReferenceExplainSnapshot;
  title?: string;
};

export function ReferenceRuleExplainSummary({ snapshot, title = '规则判断' }: Props) {
  const locked = snapshot.manual_locked ?? isReferenceManualLocked(snapshot.metadata);
  const reason = snapshot.ai_reason || snapshot.selected_reason;

  return (
    <div className="detail-section reference-explain-summary" data-testid="reference-rule-explain">
      <b>{title}</b>
      {snapshot.in_library === false && <span className="muted-hint">当前未入对标库，重评将尝试按 RuleProfile 自动入库。</span>}
      <span>
        入库状态：
        {snapshot.in_library === false ? '未入库' : `${labelReferenceLibraryType(snapshot.library_type)} · ${labelReferenceLibraryRating(snapshot.rating)}`}
      </span>
      <span>选中来源：{formatTags((snapshot.selection_sources || []).map(labelSelectionSource))}</span>
      <span>
        人工锁定：
        {locked ? <b className="tag tag-warning">是（规则重评不会覆盖）</b> : '否'}
      </span>
      <span>命中词：{formatTags(snapshot.matched_keywords)}</span>
      <span>判断原因：{reason || '-'}</span>
    </div>
  );
}

type ResultsProps = {
  results: ReferenceLibraryReevaluateResult[];
  onClear?: () => void;
};

export function ReevaluateResultPanel({ results, onClear }: ResultsProps) {
  if (results.length === 0) return null;

  return (
    <div className="detail-section reevaluate-results" data-testid="reevaluate-results">
      <div className="reevaluate-results-head">
        <b>规则重评结果</b>
        {onClear && (
          <button type="button" className="secondary compact" onClick={onClear}>
            清除
          </button>
        )}
      </div>
      <ul className="reevaluate-result-list">
        {results.map((result) => (
          <li key={`${result.content_id}-${result.status}-${result.item_id || 'none'}`} className={`reevaluate-result-item status-${result.status}`}>
            <span className="strong">{labelReevaluateStatus(result.status)}</span>
            <span className="muted">内容 {result.content_id.slice(0, 8)}…</span>
            {(result.library_type || result.rating) && (
              <span>
                {result.library_type ? labelReferenceLibraryType(result.library_type) : '-'}
                {' · '}
                {result.rating ? labelReferenceLibraryRating(result.rating) : '-'}
              </span>
            )}
            {result.reason && <span>{result.reason}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function canReevaluateReference(role: string): boolean {
  return role === 'admin' || role === 'supervisor';
}
