import { type ReactNode, useState } from 'react';

interface ChartCardProps {
  title: string;
  /** Starts collapsed? Defaults to false (open). */
  defaultOpen?: boolean;
  loading?: boolean;
  children: ReactNode;
}

/**
 * A collapsible card that hosts one canvas visualization.
 *
 * Uses the same `grid-template-rows: 0fr → 1fr` trick from SPEC.md's v1
 * (motion #6, 350ms cubic-bezier(0.5, 0, 0.2, 1)). The content wrapper has
 * `overflow: hidden` so the child collapses smoothly rather than clipping
 * at the edge.
 */
export function ChartCard({ title, defaultOpen = true, loading = false, children }: ChartCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`chart-card ${open ? 'chart-card--open' : ''}`}>
      <button
        type="button"
        className="chart-card-header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chart-card-title">{title}</span>
        <span className={`chart-card-chevron ${open ? 'chart-card-chevron--open' : ''}`} aria-hidden="true">
          ›
        </span>
      </button>
      <div className="chart-card-body">
        <div className="chart-card-content">
          {loading ? <Skeleton /> : children}
        </div>
      </div>
    </div>
  );
}

/**
 * Shimmer skeleton shown while a chart awaits data.
 * Uses the `skeleton-shimmer` keyframe from animations.css.
 */
export function Skeleton({ height = 120 }: { height?: number }) {
  return (
    <div
      className="skeleton"
      style={{ height }}
      aria-hidden="true"
      role="presentation"
    />
  );
}
