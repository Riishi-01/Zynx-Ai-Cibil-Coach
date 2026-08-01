import { useCallback, useEffect, useRef } from 'react';

import { COPY } from '../../copy';
import type { Conversation } from '../../lib/conversationStore';
import { HistorySidebar } from './HistorySidebar';

interface DockProps {
  /** Echoes the parent's hover/focus open state. */
  expanded: boolean;
  onHistoryOpenChange: (open: boolean) => void;
  onHome: () => void;
  onPickConversation: (id: string) => void;
  onClearAllHistory: () => void;
  onDeleteConversation: (id: string) => void;
  conversations: Conversation[];
  activeConversationId: string | null;
}

const COLLAPSE_DELAY_MS = 200;

/**
 * Vertical left dock. Two affordances remain: Home and History.
 *
 * Hover/focus on the History trigger expands the dock via the parent
 * (which animates a CSS grid track). 200 ms collapse delay lets the
 * cursor travel diagonally into the panel.
 */
export function Dock({
  expanded,
  onHistoryOpenChange,
  onHome,
  onPickConversation,
  onClearAllHistory,
  onDeleteConversation,
  conversations,
  activeConversationId,
}: DockProps) {
  const collapseTimerRef = useRef<number | null>(null);

  const cancelCollapse = useCallback(() => {
    if (collapseTimerRef.current !== null) {
      window.clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
  }, []);

  const openHistory = useCallback(() => {
    cancelCollapse();
    onHistoryOpenChange(true);
  }, [cancelCollapse, onHistoryOpenChange]);

  const scheduleHistoryClose = useCallback(() => {
    cancelCollapse();
    collapseTimerRef.current = window.setTimeout(() => {
      onHistoryOpenChange(false);
      collapseTimerRef.current = null;
    }, COLLAPSE_DELAY_MS);
  }, [cancelCollapse, onHistoryOpenChange]);

  useEffect(() => () => cancelCollapse(), [cancelCollapse]);

  const count = conversations.length;

  return (
    <nav
      className={`dock ${expanded ? 'dock--expanded' : ''}`}
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
        onMouseLeave={scheduleHistoryClose}
        onFocusCapture={openHistory}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            scheduleHistoryClose();
          }
        }}
      >
        <button
          type="button"
          className="dock-section dock-section--history"
          aria-label={COPY.dock.historyAria(count)}
          aria-expanded={expanded}
          aria-controls="dock-history-panel"
          title={COPY.dock.history}
        >
          <span className="dock-icon" aria-hidden="true">⏱</span>
          <span className="dock-label">{COPY.dock.history}</span>
          {count > 0 ? (
            <span className="dock-badge" aria-hidden="true">{count}</span>
          ) : null}
        </button>

        {expanded ? (
          <HistorySidebar
            conversations={conversations}
            activeId={activeConversationId}
            onPick={onPickConversation}
            onDelete={onDeleteConversation}
            onClearAll={onClearAllHistory}
          />
        ) : null}
      </div>
    </nav>
  );
}
