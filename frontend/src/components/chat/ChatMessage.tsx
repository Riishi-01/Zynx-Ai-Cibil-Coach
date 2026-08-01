import type { ChatCitation, PlanMetadata } from '../../types';
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
  /** Citations emitted by the chat RAG pipeline for this reply. */
  citations?: ChatCitation[];
  /** Token usage + cost + time for this assistant message. */
  metadata?: PlanMetadata;
  elapsedMs?: number;
  /** When set, render this assistant message as a structured plan. */
  plan?: import('../../types').PartialCoachPlan | null;
}

interface ChatMessageProps {
  message: ChatMessageData;
}

/**
 * One bubble in the chat message list.
 *
 * Role surface:
 *   user       — right-aligned, accent-tinted background.
 *   assistant  — left-aligned, soft surface with the accent stripe.
 *                  Uses MarkdownRenderer for prose, PlanView when a
 *                  `plan` is supplied.
 *   error      — centered, bad-tinted surface, plain text.
 *
 * Assistant bubbles render a MessageMetadata footer below the markdown
 * (and below any citations) so each turn carries its own model/token/cost
 * detail.
 */
export function ChatMessage({ message }: ChatMessageProps) {
  const roleClass =
    message.role === 'user'
      ? 'chat-message chat-message--user'
      : message.role === 'assistant'
        ? 'chat-message chat-message--assistant'
        : 'chat-message chat-message--error';

  return (
    <div
      className={roleClass}
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
        ) : message.role === 'error' ? (
          <p>{message.content}</p>
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
