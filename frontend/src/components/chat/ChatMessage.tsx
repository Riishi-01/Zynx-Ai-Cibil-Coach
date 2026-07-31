import type { ChatCitation } from '../../types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ChatCitations } from './ChatCitations';

export interface ChatMessageProps {
  role: 'user' | 'assistant' | 'error';
  content: string;
  streaming?: boolean;
  citations?: ChatCitation[];
}

/**
 * One bubble in the chat message list.
 *
 * User/assistant/error have distinct padding and alignment:
 *   user       — right-aligned, accent-tinted background.
 *   assistant  — left-aligned, soft surface with the accent stripe.
 *   error      — centered, bad-tinted surface, no markdown processing.
 *
 * Assistant bubbles render their content through MarkdownRenderer so the
 * streaming LaTeX/markdown buffer logic stays consistent with the analyze
 * flow. The streaming cursor appears alongside the assistant content when
 * ``streaming`` is true.
 */
export function ChatMessage({ role, content, streaming, citations }: ChatMessageProps) {
  const roleClass =
    role === 'user'
      ? 'chat-message chat-message--user'
      : role === 'assistant'
        ? 'chat-message chat-message--assistant'
        : 'chat-message chat-message--error';

  return (
    <div className={roleClass} role={role === 'error' ? 'alert' : undefined}>
      <div className="chat-message-body">
        {role === 'assistant' ? (
          <MarkdownRenderer text={content} streaming={streaming ?? false} />
        ) : (
          <p>{content}</p>
        )}
        {role === 'assistant' && streaming ? (
          <span className="streaming-cursor" aria-hidden="true">
            ▍
          </span>
        ) : null}
      </div>
      {role === 'assistant' && citations && citations.length > 0 ? (
        <ChatCitations citations={citations} />
      ) : null}
    </div>
  );
}
