import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReferenceRuleExplainSummary } from './ReferenceRuleExplain';

describe('ReferenceRuleExplainSummary', () => {
  it('renders rule trace metadata for review', () => {
    render(
      <ReferenceRuleExplainSummary
        snapshot={{
          in_library: true,
          library_type: 'non_lead',
          rating: 'good',
          selection_sources: ['ai'],
          matched_keywords: ['论文'],
          ai_reason: '命中业务关键词',
          metadata: {
            rule_profile_id: 'rule-profile-123456',
            rule_profile_version: 3,
            trigger_source: 'manual_re_evaluate',
            input_snapshot_json: {
              candidate_bucket: 'content_candidate',
              like_count: 128,
            },
          },
        }}
      />,
    );

    expect(screen.getByTestId('reference-rule-trace')).toHaveTextContent('规则版本');
    expect(screen.getByText('v3')).toBeInTheDocument();
    expect(screen.getByText('人工重评')).toBeInTheDocument();
    expect(screen.getByText('content_candidate')).toBeInTheDocument();
    expect(screen.getByText('128')).toBeInTheDocument();
  });
});
