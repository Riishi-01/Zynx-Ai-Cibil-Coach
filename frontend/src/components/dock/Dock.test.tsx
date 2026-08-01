import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Conversation } from '../../lib/conversationStore';
import { Dock } from './Dock';

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
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

describe('Dock', () => {
  let onHome: () => void;
  let onPick: (id: string) => void;
  let onDelete: (id: string) => void;
  let onClearAll: () => void;
  let onHistoryOpenChange: (open: boolean) => void;

  beforeEach(() => {
    onHome = vi.fn();
    onPick = vi.fn();
    onDelete = vi.fn();
    onClearAll = vi.fn();
    onHistoryOpenChange = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the home and history affordances', () => {
    render(
      <Dock
        expanded={false}
        onHistoryOpenChange={onHistoryOpenChange}
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
      />,
    );

    expect(
      screen.getByRole('button', { name: /return to the input form/i }),
    ).toBeInTheDocument();
    const history = screen.getByRole('button', { name: /History \(0 conversations\)/i });
    expect(history).toBeInTheDocument();
    expect(history).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows the history badge with the conversation count', () => {
    const conversations = [
      makeConversation({ id: 'c1' }),
      makeConversation({ id: 'c2' }),
    ];
    render(
      <Dock
        expanded={false}
        onHistoryOpenChange={onHistoryOpenChange}
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={conversations}
        activeConversationId={null}
      />,
    );

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('expands when the wrapper is hovered and collapses after the timer', () => {
    vi.useFakeTimers();
    render(
      <Dock
        expanded={false}
        onHistoryOpenChange={onHistoryOpenChange}
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
      />,
    );

    const nav = screen.getByRole('navigation');
    const wrapper = nav.querySelector('.dock-history-wrapper');
    if (!wrapper) throw new Error('history wrapper not found');

    fireEvent.mouseEnter(wrapper);
    expect(onHistoryOpenChange).toHaveBeenLastCalledWith(true);

    fireEvent.mouseLeave(wrapper);
    act(() => {
      vi.advanceTimersByTime(220);
    });
    expect(onHistoryOpenChange).toHaveBeenLastCalledWith(false);
  });

  it('cancels the collapse when the wrapper is re-entered', () => {
    vi.useFakeTimers();
    render(
      <Dock
        expanded={false}
        onHistoryOpenChange={onHistoryOpenChange}
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
      />,
    );

    const nav = screen.getByRole('navigation');
    const wrapper = nav.querySelector('.dock-history-wrapper');
    if (!wrapper) throw new Error('history wrapper not found');

    fireEvent.mouseEnter(wrapper);
    fireEvent.mouseLeave(wrapper);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.mouseEnter(wrapper);
    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(onHistoryOpenChange).toHaveBeenLastCalledWith(true);
  });

  it('opens the history sidebar when expanded=true', () => {
    render(
      <Dock
        expanded
        onHistoryOpenChange={onHistoryOpenChange}
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[makeConversation({ id: 'c1' })]}
        activeConversationId={'c1'}
      />,
    );
    expect(
      screen.getByRole('region', { name: /past conversations/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ABCPS\*\*\*\*A/ })).toBeInTheDocument();
  });

  it('calls onHome when the Home button is clicked', () => {
    render(
      <Dock
        expanded={false}
        onHistoryOpenChange={onHistoryOpenChange}
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /return to the input form/i }));
    expect(onHome).toHaveBeenCalledTimes(1);
  });
});
