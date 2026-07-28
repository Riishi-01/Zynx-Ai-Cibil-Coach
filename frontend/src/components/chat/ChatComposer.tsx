import { useRef, useState } from 'react';

interface ChatComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
}

/**
 * Auto-growing textarea with Enter-to-send (Shift+Enter for newline).
 * While streaming, the send button becomes a stop button (SPEC.md motion #11).
 */
export function ChatComposer({ onSend, onStop, streaming, disabled }: ChatComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || streaming || disabled) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    // Auto-grow
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  return (
    <div className="chat-composer">
      <textarea
        ref={textareaRef}
        className="chat-composer-input"
        value={value}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="Ask about your credit profile…"
        disabled={disabled || streaming}
        rows={1}
        aria-label="Chat message"
      />
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
          disabled={!value.trim() || disabled}
          aria-label="Send message"
          title="Send"
        >
          ↑
        </button>
      )}
    </div>
  );
}
