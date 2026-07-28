import type { PaymentHeatmap as HeatmapData } from '../../types';

interface PaymentHeatmapProps {
  data: HeatmapData;
}

const STATUS_COLORS = {
  0: 'var(--good)',      // on time
  1: 'var(--warn)',      // 30d late
  2: '#f97316',         // 60d late (orange)
  3: 'var(--bad)',       // 90d+ late
} as const;

const NO_DATA_COLOR = 'var(--border)';

/**
 * GitHub-contributions-style 24-month heatmap (2 rows × 12 cols).
 * Each cell's color reflects the WORST payment status across accounts for
 * that month. Hover shows the month label.
 *
 * frontend-charts-spec.md §4.
 */
export function PaymentHeatmap({ data }: PaymentHeatmapProps) {
  const pct = Math.round(data.pct_on_time * 100);
  const headlineColor = pct >= 95 ? 'var(--good)' : pct >= 80 ? 'var(--warn)' : 'var(--bad)';

  return (
    <div className="heatmap">
      <div className="heatmap-headline" style={{ color: headlineColor }}>
        <span className="heatmap-headline-pct">{pct}%</span>
        <span className="heatmap-headline-detail">
          on time ({data.months_on_time} of {data.months_total} months)
        </span>
      </div>

      <div className="heatmap-grid" role="img" aria-label={data.summary}>
        {data.cells.map((cell) => (
          <div
            key={cell.period}
            className="heatmap-cell"
            style={{
              background: cell.has_data
                ? STATUS_COLORS[cell.status as keyof typeof STATUS_COLORS] ?? NO_DATA_COLOR
                : NO_DATA_COLOR,
              opacity: cell.has_data ? 1 : 0.3,
            }}
            title={`${cell.label}: ${cell.has_data ? ['On time', '30d late', '60d late', '90d+ late'][cell.status] : 'No data'}`}
            aria-hidden="true"
          />
        ))}
      </div>

      <div className="heatmap-legend">
        <span className="heatmap-legend-item">
          <span className="heatmap-legend-dot" style={{ background: STATUS_COLORS[0] }} />
          On time
        </span>
        <span className="heatmap-legend-item">
          <span className="heatmap-legend-dot" style={{ background: STATUS_COLORS[1] }} />
          30d
        </span>
        <span className="heatmap-legend-item">
          <span className="heatmap-legend-dot" style={{ background: STATUS_COLORS[2] }} />
          60d
        </span>
        <span className="heatmap-legend-item">
          <span className="heatmap-legend-dot" style={{ background: STATUS_COLORS[3] }} />
          90d+
        </span>
      </div>

      <p className="heatmap-summary">{data.summary}</p>
    </div>
  );
}
