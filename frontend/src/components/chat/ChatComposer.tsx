import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import { COPY } from '../../copy';

export interface ChatComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
  /** When true, the composer is locked (no plan yet, hidden). */
  disabled?: boolean;
}

/**
 * Chat composer — textarea + send/stop button.
 *
 * Enter sends, Shift+Enter inserts a newline. While ``streaming`` is true
 * the send button is replaced by a stop button and the textarea is
 * disabled to prevent overlapping requests. The textarea auto-resizes up
 * to ``max-height: 160px`` so a long question doesn't push the composer
 * off-screen.
 *
 * Pass ``disabled`` to lock the composer before the analyzer has produced
 * an initial plan; the textarea shows the configured placeholder text and
 * the send button stays in the disabled state.
 */
export function ChatComposer({ onSend, onStop, streaming, disabled = false }: ChatComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!disabled) textareaRef.current?.focus();
  }, [disabled]);

  const isDisabled = disabled || streaming;

  function submit() {
    if (isDisabled) return;
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue('');
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter') return;
    if (event.shiftKey) return; // allow newline
    if (event.nativeEvent.isComposing) return; // IME safety
    event.preventDefault();
    submit();
  }

  // Auto-grow the textarea up to the 160px cap defined in chat.css.
  useLayoutEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight, 160)}px`;
  }, [value]);

  const trimmed = value.trim();
  const canSend = trimmed.length > 0 && !isDisabled;

  const placeholder = disabled
    ? COPY.composer.disabledHint
    : COPY.composer.placeholder;

  return (
    <div className="chat-composer" role="group" aria-label="Compose message">
      <textarea
        ref={textareaRef}
        className="chat-composer-textarea"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label={placeholder}
        disabled={isDisabled}
        rows={1}
      />
      {streaming ? (
        <button
          type="button"
          className="chat-composer-btn chat-composer-btn--stop"
          onClick={onStop}
          aria-label={COPY.composer.stopAria}
          title={COPY.composer.stopAria}
        >
          ■
        </button>
      ) : (
        <button
          type="button"
          className="chat-composer-btn chat-composer-btn--send"
          onClick={submit}
          disabled={!canSend}
          aria-label={disabled ? COPY.composer.disabledHint : COPY.composer.sendAria}
          title={disabled ? COPY.composer.disabledHint : COPY.composer.sendAria}
        >
          ↑
        </button>
      )}
    </div>
  );
}
