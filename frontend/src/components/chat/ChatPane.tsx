import { useEffect, useRef } from 'react';

import { useDebouncedStream } from '../../hooks/useDebouncedStream';
import { useStream } from '../../hooks/useStream';
import type { CanvasResponse, ChatHistoryTurn, PartialCoachPlan } from '../../types';
import { ChatComposer } from './ChatComposer';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ChatPaneProps {
  pan: string;
  incomeInr: number;
  onCanvasReady?: (data: CanvasResponse) => void;
  onPlanDelta?: (data: PartialCoachPlan) => void;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * The left pane: a message list + composer.
 *
 * On mount (first analysis): calls POST /api/analyze, which delivers the
 * canvas payload first (onCanvasReady hydrates the charts), then streams the
 * coaching plan as markdown via plan_delta events.
 *
 * Follow-up messages call POST /api/chat and stream markdown tokens.
 *
 * The LLM is only called when this pane mounts or the user sends a message —
 * never during chart rendering, which is fully deterministic.
 */
export function ChatPane({ pan, incomeInr, onCanvasReady, onPlanDelta }: ChatPaneProps) {
  const stream = useStream();
  const messagesRef = useRef<Message[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);

  // Debounce streaming text updates to 80ms for smooth rendering.
  const debouncedText = useDebouncedStream(stream.text, stream.streaming, 80);

  // Auto-scroll to bottom when new content arrives.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      if (isNearBottom) el.scrollTop = el.scrollHeight;
    }
  }, [debouncedText, stream.plan]);

  // Initial analysis on mount.
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    stream.send('/api/analyze', { pan, income: incomeInr }, {
      onCanvas: (data) => onCanvasReady?.(data),
      onPlanDelta: (data) => onPlanDelta?.(data),
      onDone: () => {
        // The plan is the initial assistant message, rendered from plan_delta.
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSend(message: string) {
    // Record user message.
    messagesRef.current = [...messagesRef.current, { role: 'user', content: message }];

    // Build history for context.
    const history: ChatHistoryTurn[] = messagesRef.current.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    stream.reset();
    stream.send('/api/chat', { pan, income: incomeInr, message, history }, {
      onDone: () => {
        // Record assistant response when done.
        messagesRef.current = [
          ...messagesRef.current,
          { role: 'assistant', content: stream.text },
        ];
      },
    });
  }

  // Determine what to show in the message area.
  const hasPlan = stream.plan && stream.plan.current_situation;
  const showStreamingText = stream.text.length > 0;

  return (
    <div className="chat-pane">
      <div className="chat-messages" ref={scrollRef} aria-live="polite">
        {/* Initial coaching plan rendered as structured sections */}
        {hasPlan && (
          <div className="chat-message chat-message--assistant">
            <PlanView plan={stream.plan!} />
          </div>
        )}

        {/* Follow-up conversation messages */}
        {messagesRef.current.map((msg, i) => (
          <div key={i} className={`chat-message chat-message--${msg.role}`}>
            {msg.role === 'assistant' ? (
              <MarkdownRenderer text={msg.content} />
            ) : (
              <p>{msg.content}</p>
            )}
          </div>
        ))}

        {/* Currently streaming text */}
        {showStreamingText && !hasPlan && (
          <div className="chat-message chat-message--assistant">
            <MarkdownRenderer text={debouncedText} streaming={stream.streaming} />
            {stream.streaming && <span className="streaming-cursor">▍</span>}
          </div>
        )}

        {/* Error state */}
        {stream.error && (
          <div className="chat-message chat-message--error">
            <p>{stream.error}</p>
          </div>
        )}

        {/* Empty state */}
        {!hasPlan && !showStreamingText && !stream.streaming && !stream.error && (
          <div className="chat-empty">
            <p>Ask me anything about your credit profile</p>
          </div>
        )}
      </div>

      <ChatComposer
        onSend={handleSend}
        onStop={stream.stop}
        streaming={stream.streaming}
        disabled={false}
      />
    </div>
  );
}

/**
 * Renders the structured CoachPlan sections progressively as they arrive.
 */
function PlanView({ plan }: { plan: PartialCoachPlan }) {
  return (
    <div className="plan-view">
      {plan.current_situation && (
        <div className="plan-section">
          <MarkdownRenderer text={plan.current_situation} />
        </div>
      )}

      {plan.top_actions?.map((action, i) => (
        <div key={i} className="plan-section plan-action">
          {action.title && <h3 className="plan-action-title">{action.title}</h3>}
          {action.why && <p className="plan-action-why">{action.why}</p>}
          {action.steps && (
            <ul className="plan-action-steps">
              {action.steps.map((step, j) => (
                <li key={j}>{step}</li>
              ))}
            </ul>
          )}
          {action.when_youll_see_results && (
            <p className="plan-action-timeline">⏱ {action.when_youll_see_results}</p>
          )}
        </div>
      ))}

      {plan.what_to_avoid && plan.what_to_avoid.length > 0 && (
        <div className="plan-section">
          <h3>What to avoid</h3>
          <ul>
            {plan.what_to_avoid.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {plan.follow_up_question && (
        <div className="plan-section plan-followup">
          <p>{plan.follow_up_question}</p>
        </div>
      )}
    </div>
  );
}
