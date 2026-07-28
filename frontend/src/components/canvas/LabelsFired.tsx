import type { LabelSeverity, LabelsResponse, LabelView } from '../../types';

interface LabelsFiredProps {
  data: LabelsResponse;
}

const SEVERITY_LABELS: Record<LabelSeverity, string> = {
  critical: '🔴 Critical',
  warning: '🟡 Warning',
  ok: '🟢 OK',
  excellent: '🟣 Excellent',
  info: '⚪ Info',
};

const SEVERITY_ORDER: LabelSeverity[] = ['critical', 'warning', 'ok', 'excellent', 'info'];

/**
 * All 32 labels grouped by severity, fired ones shown prominently, unfired
 * dimmed. Ordered by priority_rank within each group so the most urgent
 * label leads (resolves Conflict 4 — overlapping utilisation tiers — in
 * presentation only).
 *
 * frontend-charts-spec.md §5.
 */
export function LabelsFired({ data }: LabelsFiredProps) {
  // Group by severity, only fired ones get prominent treatment.
  const groups = new Map<LabelSeverity, LabelView[]>();
  for (const sev of SEVERITY_ORDER) {
    groups.set(sev, []);
  }

  for (const label of data.labels) {
    if (label.fired) {
      groups.get(label.severity)!.push(label);
    }
  }

  const unfired = data.labels.filter((l) => !l.fired);

  return (
    <div className="labels-fired">
      <div className="labels-fired-summary">
        <span className="labels-fired-count">{data.n_fired}</span>
        <span className="labels-fired-total">/ {data.total_labels} checks fired</span>
      </div>

      {SEVERITY_ORDER.map((sev) => {
        const items = groups.get(sev)!;
        if (items.length === 0) return null;
        return (
          <div key={sev} className="labels-fired-group">
            <div className="labels-fired-group-header">{SEVERITY_LABELS[sev]}</div>
            {items.map((label) => (
              <div key={`${label.label_id}-${label.instances[0]?.account_id ?? ''}`} className="labels-fired-item labels-fired-item--active">
                <span className="labels-fired-name">{label.display_name}</span>
                {label.instances[0]?.message && (
                  <span className="labels-fired-msg">
                    {label.instances[0].message.slice(0, 80)}
                    {label.instances[0].message.length > 80 ? '…' : ''}
                  </span>
                )}
              </div>
            ))}
          </div>
        );
      })}

      {unfired.length > 0 && (
        <details className="labels-fired-unfired">
          <summary className="labels-fired-group-header">
            ⚪ Not fired ({unfired.length})
          </summary>
          {unfired.map((label) => (
            <div key={label.label_id} className="labels-fired-item labels-fired-item--dim">
              <span className="labels-fired-name">{label.display_name}</span>
            </div>
          ))}
        </details>
      )}
    </div>
  );
}
