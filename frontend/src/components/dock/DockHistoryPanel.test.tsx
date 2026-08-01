import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { Conversation } from '../../lib/conversationStore';
import { DockHistoryPanel } from './DockHistoryPanel';

function makeConversation(overrides: Partial<Conversation>): Conversation {
  const now = new Date().toISOString();
  return {
    id: 'c1',
    panMasked: 'ABCPS****A',
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

describe('DockHistoryPanel', () => {
  it('renders the empty state when there are no conversations', () => {
    render(
      <DockHistoryPanel
        conversations={[]}
        activeId={null}
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    expect(screen.getByText(/No analyses yet/)).toBeInTheDocument();
  });

  it('renders one row per conversation', () => {
    const conversations = [
      makeConversation({ id: 'c1', panMasked: 'ABCPS****A', firstName: 'Anjali' }),
      makeConversation({ id: 'c2', panMasked: 'BCDRM****B', firstName: 'Carlos' }),
    ];
    render(
      <DockHistoryPanel
        conversations={conversations}
        activeId={null}
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    expect(screen.getByText('ABCPS****A')).toBeInTheDocument();
    expect(screen.getByText('BCDRM****B')).toBeInTheDocument();
    expect(screen.getByText(/Anjali/)).toBeInTheDocument();
    expect(screen.getByText(/Carlos/)).toBeInTheDocument();
  });

  it('marks the active row with aria-current', () => {
    const conversations = [
      makeConversation({ id: 'c1', panMasked: 'AAAAS****A' }),
      makeConversation({ id: 'c2', panMasked: 'BBBBB****B' }),
    ];
    render(
      <DockHistoryPanel
        conversations={conversations}
        activeId="c1"
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );

    const activeRow = screen
      .getByRole('button', { name: /AAAAS\*\*\*\*A/ })
      .closest('button');
    expect(activeRow).toHaveAttribute('aria-current', 'true');
    expect(
      screen.getByRole('button', { name: /BBBBB\*\*\*\*B/ }).closest('button'),
    ).not.toHaveAttribute('aria-current');
  });

  it('calls onPick, onDelete, and onClearAll from the right affordances', async () => {
    const onPick = vi.fn();
    const onDelete = vi.fn();
    const onClearAll = vi.fn();
    const user = userEvent.setup();
    const conversations = [
      makeConversation({ id: 'c1', panMasked: 'AAAAS****A' }),
      makeConversation({ id: 'c2', panMasked: 'BBBBB****B' }),
    ];
    render(
      <DockHistoryPanel
        conversations={conversations}
        activeId={null}
        onPick={onPick}
        onDelete={onDelete}
        onClearAll={onClearAll}
      />,
    );

    await user.click(
      screen.getByRole('button', { name: /AAAAS\*\*\*\*A/ }),
    );
    expect(onPick).toHaveBeenCalledWith('c1');

    const deleteButtons = screen.getAllByLabelText(/Delete conversation/i);
    await user.click(deleteButtons[0]);
    expect(onDelete).toHaveBeenCalledWith('c1');

    await user.click(screen.getByText(/Clear all/));
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it('falls back to "Unknown" when firstName is null', () => {
    const conversations = [
      makeConversation({ id: 'c1', firstName: null }),
    ];
    render(
      <DockHistoryPanel
        conversations={conversations}
        activeId={null}
        onPick={vi.fn()}
        onDelete={vi.fn()}
        onClearAll={vi.fn()}
      />,
    );
    expect(screen.getByText(/Unknown/)).toBeInTheDocument();
  });
});
