import type { PartialCoachPlan } from '../../types';
import { MarkdownRenderer } from './MarkdownRenderer';

export interface PlanViewProps {
  plan: PartialCoachPlan;
}

/**
 * Renders the structured CoachPlan sections progressively as they arrive.
 *
 * Exported both from this module and re-exported from ``ChatPane`` so the
 * existing test suite keeps finding the named export it expects. The
 * component is pure — it consumes an already-merged plan and emits DOM,
 * without any streaming of its own.
 */
export function PlanView({ plan }: PlanViewProps) {
  return (
    <div className="plan-view">
      {plan.current_situation && (
        <div className="plan-section">
          <MarkdownRenderer text={plan.current_situation} />
        </div>
      )}

      {plan.top_actions?.map((action, i) => (
        <div key={i} className="plan-section plan-action">
          {action.title && <h3 className="plan-action-title">{action.title}</h3>}
          {action.why && <p className="plan-action-why">{action.why}</p>}
          {action.steps && (
            <ul className="plan-action-steps">
              {action.steps.map((step, j) => (
                <li key={j}>{step}</li>
              ))}
            </ul>
          )}
          {action.when_youll_see_results && (
            <p className="plan-action-timeline">⏱ {action.when_youll_see_results}</p>
          )}
        </div>
      ))}

      {plan.what_to_avoid && plan.what_to_avoid.length > 0 && (
        <div className="plan-section">
          <h3>What to avoid</h3>
          <ul>
            {plan.what_to_avoid.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
