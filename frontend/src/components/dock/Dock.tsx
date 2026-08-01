/**
 * Vertical left dock. Three sections: Home, History (hover-expand), Chat.
 *
 * The dock is 56 px collapsed and 320 px when the History wrapper is
 * hovered or focused. A 200 ms collapse delay lets the cursor travel
 * into the panel without snapping shut.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { COPY } from '../../copy';
import type { Conversation } from '../../lib/conversationStore';
import { DockHistoryPanel } from './DockHistoryPanel';

interface DockProps {
  onHome: () => void;
  onPickConversation: (id: string) => void;
  onClearAllHistory: () => void;
  onDeleteConversation: (id: string) => void;
  conversations: Conversation[];
  activeConversationId: string | null;
  inSession: boolean;
  hasChatTurns: boolean;
  onClearChat: () => void;
}

const COLLAPSE_DELAY_MS = 200;

export function Dock({
  onHome,
  onPickConversation,
  onClearAllHistory,
  onDeleteConversation,
  conversations,
  activeConversationId,
  inSession,
  hasChatTurns,
  onClearChat,
}: DockProps) {
  const [isHistoryHovered, setHistoryHovered] = useState(false);
  const collapseTimerRef = useRef<number | null>(null);

  const cancelCollapse = useCallback(() => {
    if (collapseTimerRef.current !== null) {
      window.clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
  }, []);

  const scheduleCollapse = useCallback(() => {
    cancelCollapse();
    collapseTimerRef.current = window.setTimeout(() => {
      setHistoryHovered(false);
      collapseTimerRef.current = null;
    }, COLLAPSE_DELAY_MS);
  }, [cancelCollapse]);

  const openHistory = useCallback(() => {
    cancelCollapse();
    setHistoryHovered(true);
  }, [cancelCollapse]);

  // Clean up the pending collapse timer when the dock unmounts.
  useEffect(() => {
    return () => cancelCollapse();
  }, [cancelCollapse]);

  const count = conversations.length;
  const clearDisabled = !inSession || !hasChatTurns;

  return (
    <nav
      className={`dock ${isHistoryHovered ? 'dock--expanded' : ''}`}
      aria-label="Main navigation"
    >
      <button
        type="button"
        className="dock-section dock-section--home"
        onClick={onHome}
        aria-label={COPY.dock.homeAria}
        title={COPY.dock.home}
      >
        <span className="dock-icon" aria-hidden="true">⌂</span>
        <span className="dock-label">{COPY.dock.home}</span>
      </button>

      <div
        className="dock-history-wrapper"
        onMouseEnter={openHistory}
        onMouseLeave={scheduleCollapse}
        onFocusCapture={openHistory}
        onBlurCapture={(event) => {
          // Only collapse when focus leaves the wrapper itself.
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            scheduleCollapse();
          }
        }}
      >
        <button
          type="button"
          className="dock-section dock-section--history"
          aria-label={COPY.dock.historyAria(count)}
          aria-expanded={isHistoryHovered}
          title={COPY.dock.history}
        >
          <span className="dock-icon" aria-hidden="true">⏱</span>
          <span className="dock-label">{COPY.dock.history}</span>
          {count > 0 && (
            <span className="dock-badge" aria-hidden="true">{count}</span>
          )}
        </button>
        {isHistoryHovered ? (
          <DockHistoryPanel
            conversations={conversations}
            activeId={activeConversationId}
            onPick={onPickConversation}
            onDelete={onDeleteConversation}
            onClearAll={onClearAllHistory}
          />
        ) : null}
      </div>

      <button
        type="button"
        className="dock-section dock-section--chat"
        onClick={onClearChat}
        disabled={clearDisabled}
        aria-label={COPY.dock.chatAria}
        title={clearDisabled ? COPY.dock.chatDisabledHint : COPY.dock.chatAria}
      >
        <span className="dock-icon" aria-hidden="true">✎</span>
        <span className="dock-label">{COPY.dock.chat}</span>
      </button>
    </nav>
  );
}
