const OPERATION_RULE_TYPE_LABELS: Record<string, string> = {
  title: '标题规则',
  cover: '封面规则',
  body: '正文规则',
  lead: '获客规则',
  platform_risk: '平台风险',
  persona: '账号人设',
};

export const OPERATION_RULE_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  ...Object.entries(OPERATION_RULE_TYPE_LABELS).map(([value, label]) => ({ value, label })),
];

export const OPERATION_RULE_PLATFORM_OPTIONS = [
  { value: '', label: '全平台' },
  { value: 'xhs', label: '小红书' },
  { value: 'douyin', label: '抖音' },
];

export function labelOperationRuleType(value: string | null | undefined): string {
  if (!value) return '-';
  return OPERATION_RULE_TYPE_LABELS[value] || value;
}
