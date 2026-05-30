import { ChevronLeft, ChevronRight } from 'lucide-react';

type Props = {
  page: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
  disabled?: boolean;
  testId?: string;
};

export function ListPaginationBar({ page, totalPages, onPrev, onNext, disabled = false, testId }: Props) {
  return (
    <div className="pagination-bar" data-testid={testId}>
      <button type="button" className="secondary" disabled={disabled || page <= 1} onClick={onPrev}>
        <ChevronLeft size={14} />
        上一页
      </button>
      <span>
        第 {page} / {totalPages} 页
      </span>
      <button type="button" className="secondary" disabled={disabled || page >= totalPages} onClick={onNext}>
        下一页
        <ChevronRight size={14} />
      </button>
    </div>
  );
}
