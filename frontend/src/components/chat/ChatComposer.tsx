import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import { COPY } from '../../copy';

export interface ChatComposerProps {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
}

/**
 * Chat composer — textarea + send/stop button.
 *
 * Enter sends, Shift+Enter inserts a newline. While ``streaming`` is true
 * the send button is replaced by a stop button and the textarea is
 * disabled to prevent overlapping requests. The textarea auto-resizes up
 * to ``max-height: 160px`` so a long question doesn't push the composer
 * off-screen.
 */
export function ChatComposer({ onSend, onStop, streaming }: ChatComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || streaming) return;
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
  const canSend = trimmed.length > 0 && !streaming;

  return (
    <div className="chat-composer" role="group" aria-label="Ask a follow-up question">
      <textarea
        ref={textareaRef}
        className="chat-composer-textarea"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={COPY.chat.composerPlaceholder}
        aria-label={COPY.chat.composerPlaceholder}
        disabled={streaming}
        rows={1}
      />
      {streaming ? (
        <button
          type="button"
          className="chat-composer-btn chat-composer-btn--stop"
          onClick={onStop}
          aria-label={COPY.chat.stopAria}
          title={COPY.chat.stopAria}
        >
          ■
        </button>
      ) : (
        <button
          type="button"
          className="chat-composer-btn chat-composer-btn--send"
          onClick={submit}
          disabled={!canSend}
          aria-label={COPY.chat.sendAria}
          title={COPY.chat.sendAria}
        >
          ↑
        </button>
      )}
    </div>
  );
}
