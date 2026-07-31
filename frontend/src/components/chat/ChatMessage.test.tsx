import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ChatCitation } from '../../types';
import { ChatMessage } from './ChatMessage';

describe('ChatMessage', () => {
  it('renders a user bubble with plain text', () => {
    render(<ChatMessage role="user" content="How is my score?" />);
    const bubble = screen.getByText('How is my score?');
    expect(bubble).toBeInTheDocument();
  });

  it('renders an assistant bubble through markdown', () => {
    render(<ChatMessage role="assistant" content="Pay the card down." />);
    expect(screen.getByText('Pay the card down.')).toBeInTheDocument();
  });

  it('renders an error bubble with role=alert', () => {
    render(<ChatMessage role="error" content="Network failed" />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Network failed');
  });

  it('renders citations under an assistant message', () => {
    const citations: ChatCitation[] = [
      { label_id: 'maxed_out' },
      { source_title: 'CIBIL Score Factors' },
    ];
    render(
      <ChatMessage
        role="assistant"
        content="Pay down the card."
        citations={citations}
      />,
    );
    expect(screen.getByText('Maxed Out')).toBeInTheDocument();
    expect(screen.getByText('CIBIL Score Factors')).toBeInTheDocument();
  });

  it('does not render citations on user or error bubbles', () => {
    const citations: ChatCitation[] = [{ label_id: 'maxed_out' }];
    render(
      <ChatMessage role="user" content="Hello" citations={citations} />,
    );
    expect(screen.queryByText('Maxed Out')).not.toBeInTheDocument();
  });
});
