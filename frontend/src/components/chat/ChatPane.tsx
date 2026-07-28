import { useEffect, useRef, useState } from 'react';

import { COPY } from '../../copy';
import { useDebouncedStream } from '../../hooks/useDebouncedStream';
import { useStream } from '../../hooks/useStream';
import type { CanvasResponse, PartialCoachPlan } from '../../types';
import { ChatComposer } from './ChatComposer';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ModelFooter } from './ModelFooter';

interface ChatPaneProps {
  pan: string;
  incomeInr: number;
  /** Turnstile token captured at submit time, forwarded into /api/analyze. */
  turnstileToken?: string | null;
  onCanvasReady?: (data: CanvasResponse) => void;
  onPlanDelta?: (data: PartialCoachPlan) => void;
  /** Fired when the user wants to bail back to the IDLE form. */
  onRetry?: () => void;
}

/** Threshold for "is the user near the bottom of the message list?" — used by
 *  both the auto-scroll effect and the user-scroll latch so they agree. */
const NEAR_BOTTOM_PX = 100;

/**
 * The left pane: a message list + composer + model footer.
 *
 * On mount (first analysis): calls POST /api/analyze, which delivers the
 * canvas payload first (onCanvasReady hydrates the charts), then streams the
 * coaching plan as markdown via plan_delta events. The model footer fills in
 * when the metadata SSE frame arrives.
 *
 * The LLM is only called when this pane mounts — never during chart
 * rendering, which is fully deterministic.
 */
export function ChatPane({ pan, incomeInr, turnstileToken, onCanvasReady, onPlanDelta, onRetry }: ChatPaneProps) {
  const stream = useStream();
  const scrollRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  // Client-side wall-clock timing: started when the SSE request begins,
  // frozen when streaming ends. Displayed in the model footer.
  const requestStartRef = useRef<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number>(0);

  // Debounce streaming text updates to 80ms for smooth rendering.
  const debouncedText = useDebouncedStream(stream.text, stream.streaming, 80);

  // Latch user-scrolled-up so a reader mid-history isn't yanked to the bottom
  // on every new token. Cleared again once they scroll back to the bottom.
  const userScrolledUpRef = useRef(false);

  // Auto-scroll to bottom when new content arrives — unless the user has
  // explicitly scrolled up to read earlier content.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    if (userScrolledUpRef.current && !isNearBottom) return;
    el.scrollTop = el.scrollHeight;
  }, [debouncedText, stream.plan]);

  // Listen for scroll on the message list to detect a user-driven scroll-up.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    function handleScroll() {
      const isNearBottom = el!.scrollHeight - el!.scrollTop - el!.clientHeight < NEAR_BOTTOM_PX;
      userScrolledUpRef.current = !isNearBottom;
    }
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  // Freeze the elapsed timer the first time any SSE frame arrives, then again
  // when streaming ends — whichever is later.
  useEffect(() => {
    if (requestStartRef.current === null && stream.streaming) {
      requestStartRef.current = performance.now();
      return;
    }
    if (!stream.streaming && requestStartRef.current !== null && elapsedMs === 0) {
      const elapsed = performance.now() - requestStartRef.current;
      if (elapsed > 0) setElapsedMs(elapsed);
    }
  }, [stream.streaming, elapsedMs]);

  // Initial analysis on mount.
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    requestStartRef.current = performance.now();

    stream.send(
      '/api/analyze',
      { pan, income: incomeInr, turnstile_token: turnstileToken ?? undefined },
      {
        onCanvas: (data) => onCanvasReady?.(data),
        onPlanDelta: (data) => onPlanDelta?.(data),
        onDone: () => {
          // The plan is the initial assistant message, rendered from plan_delta.
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Determine what to show in the message area.
  const hasPlan = stream.plan && stream.plan.current_situation;
  const showStreamingText = stream.text.length > 0;
  const showCrunchingPlaceholder =
    stream.streaming && !hasPlan && !showStreamingText && !stream.error;
  // Reachable only when the stream completes with no plan, no text, no error
  // — a degenerate response path.
  const showEmptyNoResponse =
    !stream.streaming && !hasPlan && !showStreamingText && !stream.error;

  return (
    <div className="chat-pane">
      <div className="chat-messages" ref={scrollRef} aria-live="polite">
        {/* Initial coaching plan rendered as structured sections */}
        {hasPlan && (
          <div className="chat-message chat-message--assistant">
            <PlanView plan={stream.plan!} />
          </div>
        )}

        {/* Currently streaming text */}
        {showStreamingText && !hasPlan && (
          <div className="chat-message chat-message--assistant">
            <MarkdownRenderer text={debouncedText} streaming={stream.streaming} />
            {stream.streaming && <span className="streaming-cursor">▍</span>}
          </div>
        )}

        {/* "Crunching…" placeholder while the SSE connection is open but
            no plan_delta / canvas / text has arrived yet. */}
        {showCrunchingPlaceholder && (
          <div className="chat-empty" role="status" aria-live="polite">
            <p>{COPY.chat.crunching}</p>
          </div>
        )}

        {/* Error state */}
        {stream.error && (
          <div className="chat-message chat-message--error">
            <p>{stream.error}</p>
          </div>
        )}

        {/* Empty no-response state — only reachable on a degenerate stream
            (connection closed with no plan_delta and no error). */}
        {showEmptyNoResponse && (
          <div className="chat-empty chat-empty--centered" role="status">
            <p>{COPY.chat.emptyNoResponse}</p>
            <p>{COPY.chat.emptyNoResponseHint}</p>
            {onRetry && (
              <button type="button" onClick={onRetry}>
                {COPY.error.retry}
              </button>
            )}
          </div>
        )}
      </div>

      <ChatComposer onSend={() => {}} onStop={stream.stop} streaming={stream.streaming} />

      {/* Model + tokens + cost + elapsed-time footer. Hidden until the
          metadata SSE frame arrives. */}
      {stream.metadata && <ModelFooter metadata={stream.metadata} elapsedMs={elapsedMs} />}
    </div>
  );
}

/**
 * Renders the structured CoachPlan sections progressively as they arrive.
 *
 * Exported so the test suite can render frozen LLM output through the same
 * path the chat pane uses, without mocking SSE.
 */
export function PlanView({ plan }: { plan: PartialCoachPlan }) {
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
    </div>
  );
}
