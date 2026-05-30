import type { CustomIntelligenceScenario, IntelligenceScenario } from './scenarioPresets';
import { SYSTEM_SCENARIO_TABS } from './scenarioPresets';

type Props = {
  active: IntelligenceScenario;
  customScenarios: Array<{ id: CustomIntelligenceScenario; label: string }>;
  onChange: (scenario: IntelligenceScenario) => void;
  variant?: 'horizontal' | 'sidebar';
};

export function IntelligenceScenarioTabs({ active, customScenarios, onChange, variant = 'horizontal' }: Props) {
  return (
    <div
      className={`scenario-tabs tab-strip ${variant === 'sidebar' ? 'scenario-tabs-sidebar' : ''}`}
      data-testid="intelligence-scenario-tabs"
    >
      {SYSTEM_SCENARIO_TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`scenario-tab ${active === tab.id ? 'selected' : ''}`}
          aria-pressed={active === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
      {customScenarios.length > 0 ? <div className="scenario-tabs-divider" aria-hidden="true" /> : null}
      {customScenarios.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`scenario-tab scenario-tab-custom ${active === tab.id ? 'selected' : ''}`}
          aria-pressed={active === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
