import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { computeCost } from './cost';
import { ModelFooter } from './ModelFooter';

describe('computeCost', () => {
  it('returns the configured currency symbol and decimal precision', () => {
    // 1234 in × $0.15/1M + 567 out × $0.60/1M = $0.0005
    const cost = computeCost(1234, 567);
    expect(cost).toBe('$0.0005');
  });

  it('handles zero tokens', () => {
    expect(computeCost(0, 0)).toBe('$0.0000');
  });

  it('handles large token counts', () => {
    // 100_000 in × $0.15/1M + 50_000 out × $0.60/1M = $0.015 + $0.030 = $0.045
    expect(computeCost(100_000, 50_000)).toBe('$0.0450');
  });

  it('respects an overridden cost config', () => {
    // Different rates (e.g. for a future model switch): $1/$2 per 1M.
    const cost = computeCost(1000, 1000, {
      inputPer1M: 1,
      outputPer1M: 2,
      currencySymbol: '$',
      decimals: 6,
    });
    // 1000 × 1/1M + 1000 × 2/1M = $0.001 + $0.002 = $0.003
    expect(cost).toBe('$0.003000');
  });
});

describe('ModelFooter', () => {
  it('renders each label/value pair as a pill', () => {
    render(
      <ModelFooter
        metadata={{ model: 'gpt-4o-mini', prompt_tokens: 1234, completion_tokens: 567 }}
        elapsedMs={41000}
      />,
    );

    const footer = screen.getByLabelText('Analysis footer');
    expect(footer.textContent).toContain('Model');
    expect(footer.textContent).toContain('gpt-4o-mini');
    expect(footer.textContent).toContain('Input');
    expect(footer.textContent).toContain('1,234');
    expect(footer.textContent).toContain('Output');
    expect(footer.textContent).toContain('567');
    expect(footer.textContent).toContain('Cost');
    expect(footer.textContent).toContain('$0.0005');
    expect(footer.textContent).toContain('Time');
    expect(footer.textContent).toContain('41.0s');
  });

  it('uses en-IN grouping for token counts', () => {
    render(
      <ModelFooter
        metadata={{ model: 'gpt-4o-mini', prompt_tokens: 123456, completion_tokens: 7890 }}
        elapsedMs={0}
      />,
    );

    const footer = screen.getByLabelText('Analysis footer');
    expect(footer.textContent).toContain('1,23,456');
    expect(footer.textContent).toContain('7,890');
  });

  it('falls back to the default model display when backend omits the model', () => {
    render(
      <ModelFooter metadata={{ model: '', prompt_tokens: 0, completion_tokens: 0 }} elapsedMs={0} />,
    );

    expect(screen.getByLabelText('Analysis footer').textContent).toContain('gpt-4o-mini');
  });
});
