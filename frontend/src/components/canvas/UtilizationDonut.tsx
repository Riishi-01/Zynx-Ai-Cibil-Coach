import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';

import { formatIndianDigits } from '../../lib/format';
import type { UtilizationView as UtilData } from '../../types';

interface UtilizationDonutProps {
  data: UtilData;
}

/** Color thresholds matching frontend-charts-spec.md §3 FICO knees (but using CIBIL ranges). */
function utilColor(ratio: number): string {
  if (ratio >= 0.9) return 'var(--bad)';
  if (ratio >= 0.5) return '#ef4444cc'; // red at reduced opacity
  if (ratio >= 0.3) return 'var(--warn)';
  if (ratio >= 0.1) return 'var(--good)';
  return 'var(--good)';
}

/**
 * Donut chart showing overall utilisation %, with per-card horizontal bars
 * below (frontend-charts-spec.md §3).
 */
export function UtilizationDonut({ data }: UtilizationDonutProps) {
  const pct = Math.round(data.overall_utilization * 100);
  const used = pct;
  const free = 100 - pct;
  const pieData = [
    { name: 'Used', value: used },
    { name: 'Free', value: free },
  ];
  const mainColor = utilColor(data.overall_utilization);

  return (
    <div className="util-chart">
      <div className="util-donut-wrap">
        <ResponsiveContainer width="100%" height={140}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={42}
              outerRadius={58}
              startAngle={90}
              endAngle={-270}
              dataKey="value"
              stroke="none"
            >
              <Cell fill={mainColor} />
              <Cell fill="var(--border)" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="util-donut-center">
          <span className="util-donut-pct" style={{ color: mainColor }}>
            {pct}%
          </span>
          <span className="util-donut-label">Overall</span>
        </div>
      </div>

      {data.cards.length > 0 && (
        <div className="util-bars">
          {data.cards.map((card) => {
            const cardPct = Math.round(card.utilization * 100);
            const color = utilColor(card.utilization);
            return (
              <div key={card.account_id} className="util-bar-row">
                <span className="util-bar-name">{card.display_name}</span>
                <div className="util-bar-track">
                  <div
                    className="util-bar-fill"
                    style={{ width: `${Math.min(cardPct, 100)}%`, background: color }}
                  />
                </div>
                <span className="util-bar-pct" style={{ color }}>
                  {cardPct}%
                </span>
              </div>
            );
          })}
        </div>
      )}

      {data.callout && <p className="util-callout">{data.callout}</p>}

      {data.paydown_to_target_paise > 0 && (
        <p className="util-paydown">
          Pay ₹{formatIndianDigits(data.paydown_to_target_paise / 100)} to reach 30% overall
        </p>
      )}
    </div>
  );
}
