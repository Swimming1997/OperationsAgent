import { CheckSquare, Scale, Trash2 } from 'lucide-react';
import type { Role } from '../../types/api';
import { canReevaluateReference } from '../../components/ReferenceRuleExplain';

type Props = {
  role: Role;
  selectedCount: number;
  reevaluating: boolean;
  onBulkLeadLibrary: () => void;
  onBulkContentLibrary: () => void;
  onBulkDiscard: () => void;
  onBulkReevaluate: () => void;
};

export function IntelligenceBulkBar({
  role,
  selectedCount,
  reevaluating,
  onBulkLeadLibrary,
  onBulkContentLibrary,
  onBulkDiscard,
  onBulkReevaluate,
}: Props) {
  const canReevaluate = canReevaluateReference(role);
  const disabled = selectedCount === 0;

  return (
    <div className="bulk-bar" data-testid="intelligence-bulk-bar">
      <span>已选 {selectedCount}</span>
      <button type="button" disabled={disabled} onClick={onBulkContentLibrary}>
        <CheckSquare size={14} />
        批量入非获客库
      </button>
      <button type="button" disabled={disabled} onClick={onBulkLeadLibrary}>
        <CheckSquare size={14} />
        批量入获客库
      </button>
      <button type="button" className="secondary" disabled={disabled} onClick={onBulkDiscard}>
        <Trash2 size={14} />
        批量不合适
      </button>
      {canReevaluate && (
        <button type="button" className="secondary" disabled={disabled || reevaluating} onClick={onBulkReevaluate}>
          <Scale size={14} />
          批量规则重评
        </button>
      )}
    </div>
  );
}
