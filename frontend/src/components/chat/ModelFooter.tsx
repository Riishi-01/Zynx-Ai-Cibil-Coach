import { COPY } from '../../copy';
import { computeCost } from './cost';

interface ModelFooterProps {
  /** Token usage from the backend metadata SSE event. */
  metadata: { model: string; prompt_tokens: number; completion_tokens: number };
  /** Wall-clock duration in ms, measured client-side from request start. */
  elapsedMs: number;
}

/**
 * Format a token count with thousands separators (en-IN grouping matches
 * the rest of the UI: 12,345 not 12.345).
 */
function fmt(n: number): string {
  return new Intl.NumberFormat('en-IN').format(n);
}

/**
 * The thin footer line below the chat pane content. Renders as a row of
 * small-caps label / value pills instead of a single right-aligned terminal
 * line — distributes the metadata across the row and reads as a polish
 * footer.
 *
 * Format:
 *   MODEL  gpt-4o-mini  |  INPUT  1,234  |  OUTPUT  567  |  COST  $0.0005  |  TIME  41.0s
 *
 * `model` defaults to `COPY.analysisFooter.modelDisplay`; if the backend
 * reports a different one (e.g. after a model swap), that wins.
 */
export function ModelFooter({ metadata, elapsedMs }: ModelFooterProps) {
  const { modelDisplay } = COPY.analysisFooter;
  const modelLabel = metadata.model || modelDisplay;
  const elapsedSec = (elapsedMs / 1000).toFixed(1);
  const cost = computeCost(metadata.prompt_tokens, metadata.completion_tokens);

  return (
    <div className="model-footer" aria-label="Analysis footer">
      <span className="model-footer-pair">
        <span className="model-footer-label">Model</span>
        <span className="model-footer-value">{modelLabel}</span>
      </span>
      <span className="model-footer-sep" aria-hidden="true" />
      <span className="model-footer-pair">
        <span className="model-footer-label">Input</span>
        <span className="model-footer-value">{fmt(metadata.prompt_tokens)}</span>
      </span>
      <span className="model-footer-sep" aria-hidden="true" />
      <span className="model-footer-pair">
        <span className="model-footer-label">Output</span>
        <span className="model-footer-value">{fmt(metadata.completion_tokens)}</span>
      </span>
      <span className="model-footer-sep" aria-hidden="true" />
      <span className="model-footer-pair">
        <span className="model-footer-label">Cost</span>
        <span className="model-footer-value">{cost}</span>
      </span>
      <span className="model-footer-sep" aria-hidden="true" />
      <span className="model-footer-pair">
        <span className="model-footer-label">Time</span>
        <span className="model-footer-value">{elapsedSec}s</span>
      </span>
    </div>
  );
}
