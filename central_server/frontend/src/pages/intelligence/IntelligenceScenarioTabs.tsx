import type { IntelligenceScenario } from './scenarioPresets';
import { SCENARIO_TABS } from './scenarioPresets';

type Props = {
  active: IntelligenceScenario;
  onChange: (scenario: IntelligenceScenario) => void;
};

export function IntelligenceScenarioTabs({ active, onChange }: Props) {
  return (
    <div className="scenario-tabs tab-strip" data-testid="intelligence-scenario-tabs">
      {SCENARIO_TABS.map((tab) => (
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
    </div>
  );
}
