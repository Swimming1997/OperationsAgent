type ResourceOption = {
  value: string;
  label: string;
  description?: string;
};

type Props = {
  label: string;
  value?: string | null;
  options: ResourceOption[];
  onChange: (value: string) => void;
  allowEmpty?: boolean;
  disabled?: boolean;
  testId?: string;
};

export function ResourceSelect({ label, value, options, onChange, allowEmpty = true, disabled, testId }: Props) {
  const hasCurrentOption = Boolean(value && options.some((item) => item.value === value));
  const shouldShowSavedValue = Boolean(value && !hasCurrentOption);
  return (
    <label className="resource-field">
      <span>{label}</span>
      <select
        data-testid={testId}
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || (options.length === 0 && !shouldShowSavedValue)}
      >
        {allowEmpty && <option value="">{options.length === 0 ? '暂无可选项' : '请选择'}</option>}
        {!allowEmpty && options.length === 0 && <option value="">暂无可选项</option>}
        {shouldShowSavedValue && <option value={value || ''}>当前已保存：{value}</option>}
        {options.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}{item.description ? ` · ${item.description}` : ''}
          </option>
        ))}
      </select>
    </label>
  );
}
