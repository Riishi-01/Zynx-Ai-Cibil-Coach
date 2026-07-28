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
 * The right pane: five collapsible chart cards. Each shows a skeleton while
 * `data` is null, then renders the real chart component once the canvas
 * payload arrives from the SSE stream.
 */
export function CanvasPane({ data }: CanvasPaneProps) {
  const loading = data === null;

  return (
    <aside className="canvas-pane" aria-label="Credit profile canvas">
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

        <ChartCard title="Score Trend" loading={loading} defaultOpen={false}>
          {data && <ScoreTrendChart data={data.score_trend} />}
        </ChartCard>

        <ChartCard title="Labels Fired" loading={loading} defaultOpen={false}>
          {data && <LabelsFired data={data.labels} />}
        </ChartCard>
      </div>
    </aside>
  );
}
