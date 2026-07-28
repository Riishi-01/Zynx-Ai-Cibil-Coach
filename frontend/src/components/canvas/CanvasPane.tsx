import { COPY } from '../../copy';
import type { CanvasResponse } from '../../types';
import { ChartCard } from './ChartCard';
import { LabelsFired } from './LabelsFired';
import { PaymentHeatmap } from './PaymentHeatmap';
import { ScoreHero } from './ScoreHero';
import { ScoreTrendChart } from './ScoreTrendChart';
import { UtilizationDonut } from './UtilizationDonut';

interface CanvasPaneProps {
  data: CanvasResponse | null;
}

/**
 * The right pane: five chart cards (Score, Utilization, Payment History, Score
 * Trend, Labels Fired). Each shows a skeleton while `data` is null, then
 * renders the real chart component once the canvas payload arrives from the
 * SSE stream.
 *
 * The Labels Fired card scrolls naturally downward inside itself when
 * expanded — the `grid-template-rows: 0fr → 1fr` collapse in `ChartCard`
 * keeps the body clipped to a reasonable height.
 */
export function CanvasPane({ data }: CanvasPaneProps) {
  const loading = data === null;

  return (
    <aside className="canvas-pane" aria-label={COPY.analyzer.canvasSection}>
      <div className="canvas-pane-cards">
        <ChartCard title="Score" loading={loading} defaultOpen={true}>
          {data && <ScoreHero data={data.score_hero} />}
        </ChartCard>

        <ChartCard title="Utilization" loading={loading} defaultOpen={true}>
          {data && <UtilizationDonut data={data.utilization} />}
        </ChartCard>

        <ChartCard title="Payment History" loading={loading} defaultOpen={true}>
          {data && <PaymentHeatmap data={data.payment_heatmap} />}
        </ChartCard>

        <ChartCard title="Score Trend" loading={loading} defaultOpen={true}>
          {data && <ScoreTrendChart data={data.score_trend} />}
        </ChartCard>

        <ChartCard title="Labels Fired" loading={loading} defaultOpen={true}>
          {data && <LabelsFired data={data.labels} />}
        </ChartCard>
      </div>
    </aside>
  );
}
