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
  onOpenRules?: () => void;
};

export function ReferenceRuleExplainSummary({ snapshot, title = '规则判断', onOpenRules }: Props) {
  const locked = snapshot.manual_locked ?? isReferenceManualLocked(snapshot.metadata);
  const reason = snapshot.ai_reason || snapshot.selected_reason;

  return (
    <div className="detail-section reference-explain-summary" data-testid="reference-rule-explain">
      <b>{title}</b>
      {snapshot.in_library === false && (
        <span className="muted-hint">当前未入对标库，规则重评将按平台入选规则（RuleProfile）尝试自动入库。</span>
      )}
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
      <ReferenceRuleSettingsLink onOpenRules={onOpenRules} />
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

import {
  canArchiveReference,
  canEditReferenceLibrary,
  canReevaluateReference,
  canRevokeOwnReferenceLibraryItem,
  formatReferenceRevokeRemaining,
  isIntelligenceReadOnly,
  referenceArchiveActionLabel,
} from '../utils/intelligencePermissions';

export {
  canArchiveReference,
  canEditReferenceLibrary,
  canReevaluateReference,
  canRevokeOwnReferenceLibraryItem,
  formatReferenceRevokeRemaining,
  isIntelligenceReadOnly,
  referenceArchiveActionLabel,
};

type RuleSettingsLinkProps = {
  onOpenRules?: () => void;
};

export function ReferenceRuleSettingsLink({ onOpenRules }: RuleSettingsLinkProps) {
  if (!onOpenRules) return null;
  return (
    <button type="button" className="secondary linkish" onClick={onOpenRules}>
      查看关键词与入选规则配置
    </button>
  );
}

export function ReferencePermissionHint({
  role,
  action,
}: {
  role: string;
  action: 'archive' | 'reevaluate' | 'revoke';
}) {
  const allowed = action === 'reevaluate' ? canReevaluateReference(role) : canArchiveReference(role);
  if (allowed) return null;
  if (action === 'revoke') {
    return (
      <span className="muted-hint permission-hint">
        「撤回入库」需在入库后 24 小时内，且须为本人操作；超期请联系主管。
      </span>
    );
  }
  const label = action === 'archive' ? '移出对标库' : '规则重评';
  return <span className="muted-hint permission-hint">「{label}」需主管或管理员权限</span>;
}
