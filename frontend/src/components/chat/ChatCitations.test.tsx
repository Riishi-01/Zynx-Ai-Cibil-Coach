import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ChatCitation } from '../../types';
import { ChatCitations } from './ChatCitations';

describe('ChatCitations', () => {
  it('renders one pill per citation', () => {
    const citations: ChatCitation[] = [
      { label_id: 'maxed_out' },
      { source_title: 'CIBIL Score Factors' },
    ];
    render(<ChatCitations citations={citations} />);
    expect(screen.getByText('Maxed Out')).toBeInTheDocument();
    expect(screen.getByText('CIBIL Score Factors')).toBeInTheDocument();
  });

  it('renders nothing for empty citations', () => {
    const { container } = render(<ChatCitations citations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('skips empty entries', () => {
    const citations = [{}, { label_id: 'high_utilization' }] as ChatCitation[];
    const { container } = render(<ChatCitations citations={citations} />);
    expect(screen.getByText('High Utilization')).toBeInTheDocument();
    // Container should hold exactly the wrapper + one pill span.
    expect(container.querySelectorAll('.chat-citation-pill')).toHaveLength(1);
  });

  it('falls back to the raw label_id when the label is unknown', () => {
    const citations: ChatCitation[] = [{ label_id: 'no_such_label' }];
    render(<ChatCitations citations={citations} />);
    expect(screen.getByText('no_such_label')).toBeInTheDocument();
  });
});
