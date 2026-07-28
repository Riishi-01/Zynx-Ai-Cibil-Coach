import type { LabelSeverity, LabelsResponse, LabelView } from '../../types';

interface LabelsFiredProps {
  data: LabelsResponse;
}

interface SeverityMeta {
  label: string;
  /** CSS variable name (without var()) used for both the swatch and the item border. */
  colorVar: string;
}

const SEVERITY_META: Record<LabelSeverity, SeverityMeta> = {
  critical: { label: 'Critical', colorVar: '--bad' },
  warning: { label: 'Warning', colorVar: '--warn' },
  ok: { label: 'OK', colorVar: '--good' },
  excellent: { label: 'Excellent', colorVar: '--accent-2' },
  info: { label: 'Info', colorVar: '--accent' },
};

const SEVERITY_ORDER: LabelSeverity[] = ['critical', 'warning', 'ok', 'excellent', 'info'];

/**
 * All 32 labels grouped by severity, fired ones shown prominently, unfired
 * dimmed. Ordered by priority_rank within each group so the most urgent
 * label leads (resolves Conflict 4 — overlapping utilisation tiers — in
 * presentation only).
 *
 * Severity is conveyed by a single colored swatch per group/item — no
 * redundant bullet glyphs. The unfired group uses the strong-border token
 * for WCAG-AA contrast against the dark background.
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
        const meta = SEVERITY_META[sev];
        return (
          <div key={sev} className="labels-fired-group">
            <div className="labels-fired-group-header">
              <span
                className="labels-fired-swatch"
                style={{ background: `var(${meta.colorVar})` }}
                aria-hidden="true"
              />
              {meta.label}
            </div>
            {items.map((label) => {
              const steps = label.instances[0]?.mitigation_steps ?? [];
              return (
                <div
                  key={`${label.label_id}-${label.instances[0]?.account_id ?? ''}`}
                  className="labels-fired-item labels-fired-item--active"
                  style={{ borderLeftColor: `var(${meta.colorVar})` }}
                >
                  <span className="labels-fired-name">{label.display_name}</span>
                  {label.instances[0]?.message && (
                    <span className="labels-fired-msg">
                      {label.instances[0].message.slice(0, 80)}
                      {label.instances[0].message.length > 80 ? '…' : ''}
                    </span>
                  )}
                  {steps.length > 0 && (
                    <ul className="labels-fired-steps">
                      {steps.slice(0, 3).map((step, k) => (
                        <li key={k}>{step}</li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}

      {unfired.length > 0 && (
        <details className="labels-fired-unfired">
          <summary className="labels-fired-group-header">
            <span
              className="labels-fired-swatch"
              style={{ background: 'var(--border-strong)' }}
              aria-hidden="true"
            />
            Not fired ({unfired.length})
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
