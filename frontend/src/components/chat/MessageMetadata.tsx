import type { PlanMetadata } from '../../types';
import { fmtDuration, fmtInt } from '../../lib/format';
import { computeCost } from './cost';

export interface MessageMetadataProps {
  metadata: PlanMetadata;
  /** Wall-clock duration of this turn, ms. */
  elapsedMs: number;
  /** Override the precomputed cost string. Defaults to computeCost(). */
  cost?: string;
}

/**
 * The metadata strip rendered at the bottom of each AI message bubble.
 *
 * Format (one pipe-separated row):
 *
 *     Model: gpt-4o-mini-2024-07-18 | Input: 4,129 | Output: 535 | Cost: $0.0009 | Time: 17.6s
 *
 * Per-message so the cost of the initial plan and each chat reply stay
 * distinct (the spec's own answer to "why per-message, not one global
 * footer").
 */
export function MessageMetadata({
  metadata,
  elapsedMs,
  cost: costOverride,
}: MessageMetadataProps) {
  const cost =
    costOverride ?? computeCost(metadata.prompt_tokens, metadata.completion_tokens);

  return (
    <div
      className="message-metadata"
      aria-label="Response metadata"
    >
      <span className="message-metadata-field">
        <span className="message-metadata-label">Model:</span> {metadata.model}
      </span>
      <span className="message-metadata-sep" aria-hidden="true">|</span>
      <span className="message-metadata-field">
        <span className="message-metadata-label">Input:</span>{' '}
        {fmtInt(metadata.prompt_tokens)}
      </span>
      <span className="message-metadata-sep" aria-hidden="true">|</span>
      <span className="message-metadata-field">
        <span className="message-metadata-label">Output:</span>{' '}
        {fmtInt(metadata.completion_tokens)}
      </span>
      <span className="message-metadata-sep" aria-hidden="true">|</span>
      <span className="message-metadata-field">
        <span className="message-metadata-label">Cost:</span> {cost}
      </span>
      <span className="message-metadata-sep" aria-hidden="true">|</span>
      <span className="message-metadata-field">
        <span className="message-metadata-label">Time:</span>{' '}
        {fmtDuration(elapsedMs)}
      </span>
    </div>
  );
}
