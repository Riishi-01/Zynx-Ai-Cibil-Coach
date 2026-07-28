import { useCountUp } from '../../hooks/useCountUp';
import type { ScoreHero as ScoreHeroData, ScoreBand } from '../../types';

interface ScoreHeroProps {
  data: ScoreHeroData;
}

const BAND_COLORS: Record<ScoreBand, string> = {
  Poor: 'var(--bad)',
  Fair: 'var(--warn)',
  Good: 'var(--good)',
  'Very Good': 'var(--accent-2)',
  Excellent: 'var(--accent)',
};

/**
 * The big animated score number with band color (SPEC.md: 56px count-up,
 * 1500ms easeOutExpo), wrapped in an SVG semicircle gauge that fills to
 * `band_progress` (the customer's position within their score band).
 *
 * Geometry: 200×130 viewBox. Semicircle from 9 o'clock (180°) to 3 o'clock
 * (0°), sweeping over the top. Centre at (100, 110), radius 90. Both
 * endpoints land at y=110; the arc apex sits at y=20. The big score number
 * is centred inside the curve via flex.
 */
export function ScoreHero({ data }: ScoreHeroProps) {
  const displayScore = useCountUp(data.score, 1500, data.score_min);
  const bandColor = BAND_COLORS[data.band] ?? 'var(--fg)';

  const delta = data.score_change_3mo;
  const deltaLabel = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '—';
  const deltaColor = delta > 0 ? 'var(--good)' : delta < 0 ? 'var(--bad)' : 'var(--fg-dim)';

  // Semicircle from 180° (left, 9 o'clock) to 360° (right, 3 o'clock).
  const cx = 100;
  const cy = 110;
  const radius = 90;
  const arcCircumference = Math.PI * radius;
  const progress = Math.max(0, Math.min(1, data.band_progress));
  const arcOffset = arcCircumference * (1 - progress);

  const arcPath = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;

  return (
    <div className="score-hero">
      <div
        className="score-hero-arc-wrap"
        role="img"
        aria-label={`Score ${data.score} of ${data.score_max}, ${data.band} band, ${Math.round(progress * 100)} percent through the band`}
      >
        <svg
          className="score-hero-arc"
          viewBox="0 0 200 130"
          width="200"
          height="130"
          aria-hidden="true"
        >
          {/* Track */}
          <path
            d={arcPath}
            fill="none"
            stroke="var(--border)"
            strokeWidth="10"
            strokeLinecap="round"
          />
          {/* Fill */}
          <path
            d={arcPath}
            fill="none"
            stroke={bandColor}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={arcCircumference}
            strokeDashoffset={arcOffset}
            className="score-hero-arc-fill"
          />
        </svg>
        <div className="score-hero-number" style={{ color: bandColor }}>
          {displayScore}
        </div>
      </div>
      <div className="score-hero-band-bar" style={{ background: bandColor }} />
      <div className="score-hero-band-label" style={{ color: bandColor }}>
        {data.band}
      </div>
      <div className="score-hero-subtitle">out of {data.score_max}</div>
      {data.previous_score_3mo != null && (
        <div className="score-hero-delta" style={{ color: deltaColor }}>
          {deltaLabel} pts (3 mo)
        </div>
      )}
    </div>
  );
}
