import { useState } from 'react';

interface ChatComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
}

/**
 * Single send/stop button. The user-facing textarea was removed — there's
 * no user input in the coach flow (the LLM emits a complete plan from
 * /api/analyze). The button only toggles streaming.
 *
 * While `streaming` is true the send arrow becomes a stop button (SPEC.md
 * motion #11).
 */
export function ChatComposer({ onSend, onStop, streaming }: ChatComposerProps) {
  // State kept for future follow-up support; harmless when onSend is a no-op.
  const [value] = useState('');

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || streaming) return;
    onSend(trimmed);
  }

  return (
    <div className="chat-composer">
      {streaming ? (
        <button
          type="button"
          className="chat-composer-btn chat-composer-btn--stop"
          onClick={onStop}
          aria-label="Stop generating"
          title="Stop generating"
        >
          ■
        </button>
      ) : (
        <button
          type="button"
          className="chat-composer-btn chat-composer-btn--send"
          onClick={submit}
          disabled
          aria-label="Send message"
          title="Send"
        >
          ↑
        </button>
      )}
    </div>
  );
}
