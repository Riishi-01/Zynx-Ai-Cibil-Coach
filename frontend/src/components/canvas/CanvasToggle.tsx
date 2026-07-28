interface CanvasToggleProps {
  collapsed: boolean;
  onToggle: () => void;
}

/**
 * The chevron button in the top-right of the canvas pane that collapses it.
 * Rotates 180° in sync with the collapse animation (SPEC.md motion #7).
 * Keyboard accessible: Enter/Space, aria-expanded.
 */
export function CanvasToggle({ collapsed, onToggle }: CanvasToggleProps) {
  return (
    <button
      type="button"
      className="canvas-toggle"
      onClick={onToggle}
      aria-expanded={!collapsed}
      aria-label={collapsed ? 'Show canvas' : 'Hide canvas'}
      title={collapsed ? 'Show canvas' : 'Hide canvas'}
    >
      <span className={`canvas-toggle-icon ${collapsed ? 'canvas-toggle-icon--collapsed' : ''}`} aria-hidden="true">
        ‹
      </span>
    </button>
  );
}
