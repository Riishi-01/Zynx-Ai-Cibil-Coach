import type { ChatCitation } from '../../types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ChatCitations } from './ChatCitations';
import { MessageMetadata } from './MessageMetadata';
import { PlanView } from './PlanView';

export type ChatRole = 'user' | 'assistant' | 'error';

export interface ChatMessageData {
  id: string;
  role: ChatRole;
  content: string;
  streaming?: boolean;
  citations?: ChatCitation[];
  metadata?: import('../../types').PlanMetadata;
  elapsedMs?: number;
  plan?: import('../../types').PartialCoachPlan | null;
}

interface ChatMessageProps {
  message: ChatMessageData;
  /** Marks the message as just-finalized so the bubble can flash an accent outline. */
  highlight?: boolean;
}

/**
 * One bubble in the chat message list.
 *
 * User / assistant / error each have distinct padding and alignment.
 * Assistant bubbles render markdown (or PlanView when a `plan` is supplied)
 * with a `MessageMetadata` footer carrying per-turn token/cost/time and
 * `ChatCitations` for any source-marked tokens.
 */
export function ChatMessage({ message, highlight }: ChatMessageProps) {
  const roleClass =
    message.role === 'user'
      ? 'chat-message chat-message--user'
      : message.role === 'assistant'
        ? 'chat-message chat-message--assistant'
        : 'chat-message chat-message--error';

  const isFinalized = highlight && message.role === 'assistant' && !message.streaming;

  return (
    <div
      className={`${roleClass}${isFinalized ? ' chat-message--finalized' : ''}`}
      role={message.role === 'error' ? 'alert' : undefined}
      data-message-id={message.id}
    >
      <div className="chat-message-body">
        {message.role === 'assistant' ? (
          message.plan ? (
            <PlanView plan={message.plan} />
          ) : (
            <>
              <MarkdownRenderer
                text={message.content}
                streaming={message.streaming ?? false}
              />
              {message.streaming ? (
                <span className="streaming-cursor" aria-hidden="true">
                  ▍
                </span>
              ) : null}
            </>
          )
        ) : (
          <p>{message.content}</p>
        )}
      </div>
      {message.role === 'assistant' &&
        !message.streaming &&
        message.metadata &&
        message.elapsedMs !== undefined ? (
        <MessageMetadata metadata={message.metadata} elapsedMs={message.elapsedMs} />
      ) : null}
      {message.role === 'assistant' &&
        message.citations &&
        message.citations.length > 0 &&
        !message.plan ? (
        <ChatCitations citations={message.citations} />
      ) : null}
    </div>
  );
}
