import { COPY } from '../../copy';
import { fmtRelative } from '../../lib/format';
import type { Conversation } from '../../lib/conversationStore';

interface DockHistoryPanelProps {
  conversations: Conversation[];
  activeId: string | null;
  onPick: (id: string) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
}

/**
 * The list of past conversations rendered inside the History dock section.
 *
 * Empty state, per-item row with delete affordance, and a footer
 * "Clear all" link. Each item is keyed by conversation id so React
 * preserves the row identity across updates.
 */
export function DockHistoryPanel({
  conversations,
  activeId,
  onPick,
  onDelete,
  onClearAll,
}: DockHistoryPanelProps) {
  const items = conversations;

  return (
    <div className="dock-history-panel" role="region" aria-label="Past conversations">
      <div className="dock-history-header">{COPY.dock.history}</div>

      {items.length === 0 ? (
        <div className="dock-history-empty">{COPY.dock.historyEmpty}</div>
      ) : (
        <ul className="dock-history-list">
          {items.map((conv) => {
            const labelId = `dock-item-${conv.id}`;
            const isActive = conv.id === activeId;
            return (
              <li
                key={conv.id}
                className={`dock-history-item${isActive ? ' dock-history-item--active' : ''}`}
              >
                <button
                  id={labelId}
                  type="button"
                  className="dock-history-item-main"
                  onClick={() => onPick(conv.id)}
                  aria-current={isActive ? 'true' : undefined}
                >
                  <div className="dock-history-pan">{conv.panMasked}</div>
                  <div className="dock-history-name">
                    {(conv.firstName ?? 'Unknown')} · {fmtRelative(conv.updatedAt)}
                  </div>
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

      {items.length > 0 ? (
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
