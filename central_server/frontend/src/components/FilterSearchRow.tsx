import { Search } from 'lucide-react';

type Props = {
  id: string;
  label: string;
  value: string;
  appliedQuery: string;
  placeholder?: string;
  layout?: 'stacked' | 'inline';
  onChange: (value: string) => void;
  onSearch: () => void;
  onClear: () => void;
  clearLabel?: (query: string) => string;
};

export function FilterSearchRow({
  id,
  label,
  value,
  appliedQuery,
  placeholder = '输入后点「搜索」或回车',
  layout = 'stacked',
  onChange,
  onSearch,
  onClear,
  clearLabel = (query) => `清除搜索「${query}」`,
}: Props) {
  const input = (
    <input
      id={id}
      value={value}
      aria-label={layout === 'inline' ? label : undefined}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => event.key === 'Enter' && onSearch()}
      placeholder={layout === 'inline' ? placeholder || label : placeholder}
    />
  );

  if (layout === 'inline') {
    return (
      <div className="filter-search-inline" data-testid={`${id}-inline`}>
        <div className="filter-search-row">
          {input}
          <button type="button" className="secondary" onClick={onSearch} title="搜索">
            <Search size={14} />
            搜索
          </button>
        </div>
        {appliedQuery ? (
          <button type="button" className="secondary linkish filter-search-clear" onClick={onClear}>
            {clearLabel(appliedQuery)}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <label htmlFor={id}>{label}</label>
      <div className="filter-search-row">
        {input}
        <button type="button" className="secondary" onClick={onSearch} title="搜索">
          <Search size={14} />
          搜索
        </button>
      </div>
      {appliedQuery ? (
        <button type="button" className="secondary linkish" onClick={onClear}>
          {clearLabel(appliedQuery)}
        </button>
      ) : null}
    </>
  );
}
