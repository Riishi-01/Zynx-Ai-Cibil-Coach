import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ChatCitation } from '../../types';
import { ChatMessage, type ChatMessageData } from './ChatMessage';

describe('ChatMessage', () => {
  const baseMessage: ChatMessageData = {
    id: 'm1',
    role: 'user',
    content: 'How is my score?',
  };

  it('renders a user bubble with plain text', () => {
    render(<ChatMessage message={baseMessage} />);
    const bubble = screen.getByText('How is my score?');
    expect(bubble).toBeInTheDocument();
  });

  it('renders an assistant bubble through markdown', () => {
    render(
      <ChatMessage
        message={{
          ...baseMessage,
          id: 'a1',
          role: 'assistant',
          content: 'Pay the card down.',
        }}
      />,
    );
    expect(screen.getByText('Pay the card down.')).toBeInTheDocument();
  });

  it('renders an error bubble with role=alert', () => {
    render(
      <ChatMessage
        message={{
          ...baseMessage,
          id: 'e1',
          role: 'error',
          content: 'Network failed',
        }}
      />,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Network failed');
  });

  it('renders citations under an assistant message when not in plan mode', () => {
    const citations: ChatCitation[] = [
      { label_id: 'maxed_out' },
      { source_title: 'CIBIL Score Factors' },
    ];
    render(
      <ChatMessage
        message={{
          ...baseMessage,
          id: 'a2',
          role: 'assistant',
          content: 'Pay down the card.',
          citations,
        }}
      />,
    );
    expect(screen.getByText('Maxed Out')).toBeInTheDocument();
    expect(screen.getByText('CIBIL Score Factors')).toBeInTheDocument();
  });

  it('does not render citations on user or error bubbles', () => {
    const citations: ChatCitation[] = [{ label_id: 'maxed_out' }];
    render(
      <ChatMessage
        message={{ ...baseMessage, citations }}
      />,
    );
    expect(screen.queryByText('Maxed Out')).not.toBeInTheDocument();
  });

  it('renders the metadata footer when streaming is off and metadata is set', () => {
    render(
      <ChatMessage
        message={{
          ...baseMessage,
          id: 'md1',
          role: 'assistant',
          content: 'Pay down the card.',
          metadata: {
            model: 'gpt-4o-mini-2024-07-18',
            prompt_tokens: 100,
            completion_tokens: 50,
          },
          elapsedMs: 1500,
        }}
      />,
    );
    expect(screen.getByText(/Model:/)).toBeInTheDocument();
  });

  it('hides the metadata footer while the assistant message is still streaming', () => {
    render(
      <ChatMessage
        message={{
          ...baseMessage,
          id: 'md2',
          role: 'assistant',
          content: 'tokens flying…',
          streaming: true,
          metadata: {
            model: 'gpt-4o-mini-2024-07-18',
            prompt_tokens: 100,
            completion_tokens: 50,
          },
          elapsedMs: 1500,
        }}
      />,
    );
    expect(screen.queryByText(/Model:/)).not.toBeInTheDocument();
  });
});
