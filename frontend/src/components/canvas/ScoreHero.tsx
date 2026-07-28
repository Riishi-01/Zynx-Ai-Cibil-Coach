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
 * 1500ms easeOutExpo, "out of 900" subtitle, thin colored band underneath).
 */
export function ScoreHero({ data }: ScoreHeroProps) {
  const displayScore = useCountUp(data.score, 1500, data.score_min);
  const bandColor = BAND_COLORS[data.band] ?? 'var(--fg)';

  const delta = data.score_change_3mo;
  const deltaLabel = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '—';
  const deltaColor = delta > 0 ? 'var(--good)' : delta < 0 ? 'var(--bad)' : 'var(--fg-dim)';

  return (
    <div className="score-hero">
      <div className="score-hero-number" style={{ color: bandColor }}>
        {displayScore}
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
