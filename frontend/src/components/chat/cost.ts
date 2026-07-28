/**
 * Cost computation for the analysis footer.
 *
 * Pricing lives in `COPY.analysisFooter.cost` so a PM can update rates
 * without code changes. Pricing is per-1M tokens in USD; we divide by
 * 1,000,000 to get per-token cost.
 */

import { COPY } from '../../copy';

/**
 * Compute the USD cost of a single analysis using the standard text pricing
 * baked into copy.ts. Rounded to the configured decimal places (e.g. 4 -> "$0.0005").
 */
export function computeCost(
  promptTokens: number,
  completionTokens: number,
  cost = COPY.analysisFooter.cost,
): string {
  const usd =
    promptTokens * (cost.inputPer1M / 1_000_000) +
    completionTokens * (cost.outputPer1M / 1_000_000);
  return `${cost.currencySymbol}${usd.toFixed(cost.decimals)}`;
}
