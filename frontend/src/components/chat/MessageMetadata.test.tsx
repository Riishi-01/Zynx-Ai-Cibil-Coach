import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { PlanMetadata } from '../../types';
import { MessageMetadata } from './MessageMetadata';

const SAMPLE_METADATA: PlanMetadata = {
  model: 'gpt-4o-mini-2024-07-18',
  prompt_tokens: 4129,
  completion_tokens: 535,
};

describe('MessageMetadata', () => {
  it('renders every labelled field', () => {
    render(
      <MessageMetadata metadata={SAMPLE_METADATA} elapsedMs={17_600} />,
    );

    expect(screen.getByText(/Model:/)).toBeInTheDocument();
    expect(screen.getByText(SAMPLE_METADATA.model)).toBeInTheDocument();
    expect(screen.getByText(/Input:/)).toBeInTheDocument();
    expect(screen.getByText(/Output:/)).toBeInTheDocument();
    expect(screen.getByText(/Cost:/)).toBeInTheDocument();
    expect(screen.getByText(/Time:/)).toBeInTheDocument();
  });

  it('uses en-IN grouping for token counts', () => {
    render(
      <MessageMetadata metadata={SAMPLE_METADATA} elapsedMs={17_600} />,
    );

    expect(screen.getByText('4,129')).toBeInTheDocument();
    expect(screen.getByText('535')).toBeInTheDocument();
  });

  it('formats elapsed ms as decimal seconds', () => {
    render(
      <MessageMetadata metadata={SAMPLE_METADATA} elapsedMs={17_600} />,
    );

    expect(screen.getByText('17.6s')).toBeInTheDocument();
  });

  it('computes cost from the metadata by default', () => {
    render(
      <MessageMetadata metadata={SAMPLE_METADATA} elapsedMs={17_600} />,
    );

    // 4129 input × $0.15/1M + 535 output × $0.6/1M → $0.0009 at 4-decimal.
    expect(screen.getByText('$0.0009')).toBeInTheDocument();
  });

  it('honors a caller-supplied cost string', () => {
    render(
      <MessageMetadata
        metadata={SAMPLE_METADATA}
        elapsedMs={3_000}
        cost="$0.0019"
      />,
    );

    expect(screen.getByText('$0.0019')).toBeInTheDocument();
    expect(screen.queryByText('$0.0009')).not.toBeInTheDocument();
  });

  it('renders four pipe separators between five fields', () => {
    const { container } = render(
      <MessageMetadata metadata={SAMPLE_METADATA} elapsedMs={17_600} />,
    );
    const seps = container.querySelectorAll('.message-metadata-sep');
    expect(seps).toHaveLength(4);
  });

  it('exposes an aria-label for the strip', () => {
    render(
      <MessageMetadata metadata={SAMPLE_METADATA} elapsedMs={17_600} />,
    );

    expect(screen.getByLabelText('Response metadata')).toBeInTheDocument();
  });
});
