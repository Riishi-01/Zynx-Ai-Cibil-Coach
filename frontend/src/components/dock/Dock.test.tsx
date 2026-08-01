import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Conversation } from '../../lib/conversationStore';
import { COPY } from '../../copy';
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
  let onClearChat: () => void;

  beforeEach(() => {
    onHome = vi.fn();
    onPick = vi.fn();
    onDelete = vi.fn();
    onClearAll = vi.fn();
    onClearChat = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the three dock sections', () => {
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
        inSession={false}
        hasChatTurns={false}
        onClearChat={onClearChat}
      />,
    );

    expect(
      screen.getByRole('button', { name: COPY.dock.homeAria }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: COPY.dock.historyAria(0) }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: COPY.dock.chatAria }),
    ).toBeInTheDocument();
  });

  it('shows the history badge with the conversation count', () => {
    const conversations = [
      makeConversation({ id: 'c1' }),
      makeConversation({ id: 'c2' }),
    ];
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={conversations}
        activeConversationId={null}
        inSession={false}
        hasChatTurns={false}
        onClearChat={onClearChat}
      />,
    );

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('expands the dock while the History wrapper is hovered', async () => {
    vi.useFakeTimers();
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[makeConversation()]}
        activeConversationId={null}
        inSession={false}
        hasChatTurns={false}
        onClearChat={onClearChat}
      />,
    );

    const nav = screen.getByRole('navigation');
    expect(nav.classList.contains('dock--expanded')).toBe(false);

    const wrapper = nav.querySelector('.dock-history-wrapper');
    if (!wrapper) throw new Error('history wrapper not found');
    fireEvent.mouseEnter(wrapper);
    expect(nav.classList.contains('dock--expanded')).toBe(true);

    fireEvent.mouseLeave(wrapper);
    act(() => {
      vi.advanceTimersByTime(220);
    });
    expect(nav.classList.contains('dock--expanded')).toBe(false);
  });

  it('clears the collapse timer when the user re-enters the wrapper', () => {
    vi.useFakeTimers();
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[makeConversation()]}
        activeConversationId={null}
        inSession={false}
        hasChatTurns={false}
        onClearChat={onClearChat}
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
    // Re-entering should have reset the timer; it should still be expanded.
    expect(nav.classList.contains('dock--expanded')).toBe(true);
  });

  it('calls onHome when the Home button is clicked', async () => {
    const user = userEvent.setup();
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
        inSession={false}
        hasChatTurns={false}
        onClearChat={onClearChat}
      />,
    );
    await user.click(screen.getByRole('button', { name: COPY.dock.homeAria }));
    expect(onHome).toHaveBeenCalledTimes(1);
  });

  it('disables the chat clear button when there are no chat turns', () => {
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
        inSession={true}
        hasChatTurns={false}
        onClearChat={onClearChat}
      />,
    );
    expect(
      screen.getByRole('button', { name: COPY.dock.chatAria }),
    ).toBeDisabled();
  });

  it('exposes a clear action when a session has chat turns', () => {
    render(
      <Dock
        onHome={onHome}
        onPickConversation={onPick}
        onClearAllHistory={onClearAll}
        onDeleteConversation={onDelete}
        conversations={[]}
        activeConversationId={null}
        inSession={true}
        hasChatTurns={true}
        onClearChat={onClearChat}
      />,
    );
    const button = screen.getByRole('button', { name: COPY.dock.chatAria });
    expect(button).toBeEnabled();
  });
});
