import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { COPY } from '../../copy';
import type { Conversation } from '../../lib/conversationStore';
import { HistorySidebar } from './HistorySidebar';

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  const now = new Date().toISOString();
  return {
    id: 'c1',
    panMasked: 'AAAAS****A',
    firstName: 'Anjali',
    incomeInr: 75000,
    canvas: null,
    initialPlan: null,
    initialMetadata: null,
    elapsedMs: 0,
    turns: [],
    createdAt: now,
    updatedAt: now,
    ...overrides,
  };
}

describe('HistorySidebar', () => {
  it('renders the empty state when there are no conversations', () => {
    render(
      <HistorySidebar
        conversations={[]}
        activeId={null}
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    expect(
      screen.getByText(COPY.dock.historyEmpty),
    ).toBeInTheDocument();
  });

  it('falls back to the customer name when no chat turns exist yet', () => {
    render(
      <HistorySidebar
        conversations={[makeConversation({ id: 'c1', turns: [] })]}
        activeId={'c1'}
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    expect(screen.getByText(/Anjali — credit analysis/i)).toBeInTheDocument();
    expect(screen.getByText('AAAAS****A')).toBeInTheDocument();
  });

  it('uses the most recent user turn as the title', () => {
    render(
      <HistorySidebar
        conversations={[
          makeConversation({
            id: 'c1',
            turns: [
              { role: 'user', content: 'When will my score drop by 30?' },
            ],
          }),
        ]}
        activeId="c1"
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    expect(screen.getByText('When will my score drop by 30?')).toBeInTheDocument();
  });

  it('marks the active row with aria-current', () => {
    render(
      <HistorySidebar
        conversations={[
          makeConversation({ id: 'c1', panMasked: 'AAAAS****A' }),
          makeConversation({ id: 'c2', panMasked: 'BBBBB****B' }),
        ]}
        activeId="c1"
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    const active = screen.getByRole('button', { name: /AAAAS\*\*\*\*A/ });
    expect(active).toHaveAttribute('aria-current', 'true');
    const inactive = screen.getByRole('button', { name: /BBBBB\*\*\*\*B/ });
    expect(inactive).not.toHaveAttribute('aria-current');
  });

  it('calls onPick, onDelete, and onClearAll via the right affordances', async () => {
    const onPick = vi.fn();
    const onDelete = vi.fn();
    const onClearAll = vi.fn();
    const user = userEvent.setup();
    render(
      <HistorySidebar
        conversations={[
          makeConversation({ id: 'c1', panMasked: 'AAAAS****A' }),
          makeConversation({ id: 'c2', panMasked: 'BBBBB****B' }),
        ]}
        activeId={null}
        onPick={onPick}
        onDelete={onDelete}
        onClearAll={onClearAll}
      />,
    );

    await user.click(screen.getByRole('button', { name: /AAAAS\*\*\*\*A/ }));
    expect(onPick).toHaveBeenCalledWith('c1');

    const deleteButtons = screen.getAllByLabelText(/delete conversation/i);
    await user.click(deleteButtons[0]);
    expect(onDelete).toHaveBeenCalledWith('c1');

    await user.click(screen.getByText(/clear all/i));
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });
});
