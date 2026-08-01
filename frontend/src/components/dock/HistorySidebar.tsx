import { COPY } from '../../copy';
import { fmtRelative } from '../../lib/format';
import type { Conversation } from '../../lib/conversationStore';

interface HistorySidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onPick: (id: string) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
}

const MASK_FULL_PAN = (value: string): string => value || '';

/**
 * ChatGPT-style history list. Two-line rows: title (preview or
 * customer name) + relative timestamp. The delete affordance is
 * invisible until the row is hovered.
 */
export function HistorySidebar({
  conversations,
  activeId,
  onPick,
  onDelete,
  onClearAll,
}: HistorySidebarProps) {
  return (
    <div
      id="dock-history-panel"
      className="dock-history-panel"
      role="region"
      aria-label="Past conversations"
    >
      <div className="dock-history-header">{COPY.dock.history}</div>

      {conversations.length === 0 ? (
        <div className="dock-history-empty">{COPY.dock.historyEmpty}</div>
      ) : (
        <ul className="dock-history-list">
          {conversations.map((conv) => {
            const title = pickTitle(conv);
            const isActive = conv.id === activeId;
            return (
              <li
                key={conv.id}
                className={`dock-history-item${isActive ? ' dock-history-item--active' : ''}`}
              >
                <button
                  type="button"
                  className="dock-history-item-main"
                  onClick={() => onPick(conv.id)}
                  aria-current={isActive ? 'true' : undefined}
                  title={title}
                >
                  <span className="dock-history-item-title">{title}</span>
                  <span className="dock-history-item-subtitle">
                    <span className="dock-history-item-pan">{MASK_FULL_PAN(conv.panMasked)}</span>
                    <span className="dock-history-item-time">
                      {fmtRelative(conv.updatedAt)}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  className="dock-history-item-delete"
                  onClick={() => onDelete(conv.id)}
                  aria-label={COPY.dock.historyDelete}
                  title={COPY.dock.historyDelete}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {conversations.length > 0 ? (
        <div className="dock-history-footer">
          <button
            type="button"
            className="dock-history-clear-all"
            onClick={onClearAll}
          >
            {COPY.dock.historyClearAll}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function pickTitle(conv: Conversation): string {
  const lastUser = [...conv.turns].reverse().find((turn) => turn.role === 'user');
  if (lastUser && lastUser.content.trim().length > 0) {
    return truncate(lastUser.content.trim(), 60);
  }
  if (conv.firstName && conv.firstName.trim().length > 0) {
    return `${conv.firstName.trim()} — credit analysis`;
  }
  return 'Credit analysis';
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max - 1).trimEnd()}…`;
}
