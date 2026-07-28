import { Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';

import type { ScoreTrend as ScoreTrendData } from '../../types';

interface ScoreTrendProps {
  data: ScoreTrendData;
}

const TREND_COLORS = {
  rising: 'var(--good)',
  falling: 'var(--bad)',
  stable: 'var(--fg-dim)',
} as const;

const TREND_GLYPHS = {
  rising: '↑',
  falling: '↓',
  stable: '→',
} as const;

/**
 * 3-point line chart showing score trajectory (frontend-charts-spec.md §2).
 * Color and delta chip change by trend direction; annotation below when notable.
 */
export function ScoreTrendChart({ data }: ScoreTrendProps) {
  const color = TREND_COLORS[data.trend as keyof typeof TREND_COLORS] ?? TREND_COLORS.stable;
  const glyph = TREND_GLYPHS[data.trend as keyof typeof TREND_GLYPHS] ?? '→';

  // Filter out null scores so the line doesn't connect through gaps.
  const chartData = data.points.map((p) => ({
    name: p.label,
    score: p.score,
  }));

  // Determine Y axis domain from the points that have data.
  const scores = data.points.filter((p) => p.score != null).map((p) => p.score!);
  const minScore = scores.length ? Math.max(300, Math.min(...scores) - 30) : 300;
  const maxScore = scores.length ? Math.min(900, Math.max(...scores) + 30) : 900;

  const delta = data.change_3mo;
  const deltaLabel = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '0';
  const hasDelta = delta !== 0;

  return (
    <div className="score-trend">
      <div className="score-trend-header">
        <span className="score-trend-chip" style={{ color, borderColor: color }}>
          {glyph} {hasDelta ? `${deltaLabel} pts` : 'No change'}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={100}>
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <XAxis
            dataKey="name"
            tick={{ fill: 'var(--fg-dim)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis domain={[minScore, maxScore]} hide />
          <Line
            type="monotone"
            dataKey="score"
            stroke={color}
            strokeWidth={2}
            dot={{ r: 4, fill: color, stroke: 'var(--bg-elev)', strokeWidth: 2 }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>

      {data.annotation && (
        <p className="score-trend-annotation" style={{ color }}>
          {data.annotation}
        </p>
      )}
    </div>
  );
}
