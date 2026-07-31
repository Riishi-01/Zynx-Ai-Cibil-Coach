import { useCallback, useEffect, useRef, useState } from 'react';

import { COPY } from '../../copy';
import { useStream } from '../../hooks/useStream';
import type { CanvasResponse, ChatCitation, PartialCoachPlan } from '../../types';
import { ChatComposer } from './ChatComposer';
import { ChatMessage } from './ChatMessage';
import { ModelFooter } from './ModelFooter';
import { PlanView } from './PlanView';

interface ChatPaneProps {
  pan: string;
  incomeInr: number;
  /** Turnstile token captured at submit time, forwarded into /api/analyze and /api/chat. */
  turnstileToken?: string | null;
  onCanvasReady?: (data: CanvasResponse) => void;
  onPlanDelta?: (data: PartialCoachPlan) => void;
  /** Fired when the user wants to bail back to the IDLE form. */
  onRetry?: () => void;
}

interface FollowUpMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  content: string;
  streaming?: boolean;
  citations?: ChatCitation[];
}

const NEAR_BOTTOM_PX = 80;

function buildId() {
  return Math.random().toString(36).slice(2);
}

/**
 * The chat pane: hydrated plan + follow-up messages + composer + footer.
 *
 * Uses two independent ``useStream`` instances so a follow-up chat request
 * doesn't reset the analyze stream's cached canvas, plan, or metadata.
 *
 * Token accumulation lives in a ref + per-message state update path so the
 * active assistant bubble shows the running text on each frame without
 * triggering a render storm through the debounced text buffer.
 */
export function ChatPane({ pan, incomeInr, turnstileToken, onCanvasReady, onPlanDelta }: ChatPaneProps) {
  const analyze = useStream();
  const followup = useStream();
  const scrollRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<FollowUpMessage[]>([]);
  const [messages, setMessages] = useState<FollowUpMessage[]>([]);
  const activeMessageIdRef = useRef<string | null>(null);
  const userScrolledUpRef = useRef(false);
  const requestStartRef = useRef<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const initializedAnalyzeRef = useRef(false);

  // Mirror messages into a ref so streaming handlers see the latest state
  // without taking their snapshot-time version.
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  function patchMessages(updater: (list: FollowUpMessage[]) => FollowUpMessage[]) {
    const next = updater(messagesRef.current);
    messagesRef.current = next;
    setMessages(next);
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isNearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    if (userScrolledUpRef.current && !isNearBottom) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, analyze.plan]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    function handleScroll() {
      const isNearBottom =
        el!.scrollHeight - el!.scrollTop - el!.clientHeight < NEAR_BOTTOM_PX;
      userScrolledUpRef.current = !isNearBottom;
    }
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (requestStartRef.current === null && analyze.streaming) {
      requestStartRef.current = performance.now();
      return;
    }
    if (
      !analyze.streaming &&
      requestStartRef.current !== null &&
      elapsedMs === 0
    ) {
      const elapsed = performance.now() - requestStartRef.current;
      if (elapsed > 0) setElapsedMs(elapsed);
    }
  }, [analyze.streaming, elapsedMs]);

  function appendUserMessage(content: string) {
    const id = buildId();
    patchMessages((prev) => [
      ...prev,
      { id, role: 'user', content },
    ]);
    return id;
  }

  function startAssistantPlaceholder(): string {
    const id = buildId();
    activeMessageIdRef.current = id;
    patchMessages((prev) => [
      ...prev,
      { id, role: 'assistant', content: '', streaming: true },
    ]);
    return id;
  }

  function patchActiveMessage(updater: (m: FollowUpMessage) => FollowUpMessage) {
    const id = activeMessageIdRef.current;
    if (!id) return;
    patchMessages((prev) =>
      prev.map((m) => (m.id === id ? updater(m) : m)),
    );
  }

  function finishActive() {
    activeMessageIdRef.current = null;
  }

  const handleFollowupToken = useCallback(
    (chunk: string) => {
      if (!activeMessageIdRef.current) return;
      patchActiveMessage((m) => ({ ...m, content: m.content + chunk }));
    },
    [],
  );

  const handleFollowupCitations = useCallback((citations: ChatCitation[]) => {
    if (!activeMessageIdRef.current) return;
    patchActiveMessage((m) => ({ ...m, citations }));
  }, []);

  const handleFollowupGuardrail = useCallback((info: { verdict: string }) => {
    if (info.verdict !== 'out_of_scope') return;
    if (!activeMessageIdRef.current) return;
    patchActiveMessage((m) => ({
      ...m,
      content: COPY.chat.outOfScope,
      citations: undefined,
      streaming: false,
    }));
    finishActive();
  }, []);

  const handleFollowupReplace = useCallback((content: string) => {
    if (!activeMessageIdRef.current) return;
    patchActiveMessage((m) => ({
      ...m,
      content,
      citations: undefined,
      streaming: false,
    }));
    finishActive();
  }, []);

  useEffect(() => {
    if (!followup.error) return;
    if (!activeMessageIdRef.current) return;
    patchActiveMessage((m) => ({
      ...m,
      role: 'error',
      content: followup.error ?? 'Error',
      streaming: false,
    }));
    finishActive();
  }, [followup.error]);

  useEffect(() => {
    if (!followup.done) return;
    if (!activeMessageIdRef.current) return;
    patchActiveMessage((m) => ({ ...m, streaming: false }));
    finishActive();
  }, [followup.done]);

  // Initial analyze call on mount.
  useEffect(() => {
    if (initializedAnalyzeRef.current) return;
    initializedAnalyzeRef.current = true;
    requestStartRef.current = performance.now();
    analyze.send(
      '/api/analyze',
      { pan, income: incomeInr, turnstile_token: turnstileToken ?? undefined },
      {
        onCanvas: (data) => onCanvasReady?.(data),
        onPlanDelta: (data) => onPlanDelta?.(data),
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSend = useCallback(
    (message: string) => {
      if (followup.streaming) return;
      appendUserMessage(message);
      startAssistantPlaceholder();

      const history = messagesRef.current
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .filter((m) => !m.streaming)
        .map((m) => ({ role: m.role, content: m.content }));

      followup.send(
        '/api/chat',
        {
          pan,
          income: incomeInr,
          message,
          history,
          turnstile_token: turnstileToken ?? undefined,
        },
        {
          onToken: handleFollowupToken,
          onCitations: handleFollowupCitations,
          onGuardrail: handleFollowupGuardrail,
          onReplace: handleFollowupReplace,
        },
      );
    },
    [
      followup,
      pan,
      incomeInr,
      turnstileToken,
      handleFollowupToken,
      handleFollowupCitations,
      handleFollowupGuardrail,
      handleFollowupReplace,
    ],
  );

  const hasPlan = !!analyze.plan && !!analyze.plan.current_situation;
  const showCrunching = analyze.streaming && !hasPlan && !analyze.error;

  return (
    <div className="chat-pane">
      <div className="chat-messages" ref={scrollRef} aria-live="polite">
        {hasPlan ? (
          <div className="chat-message chat-message--assistant">
            <PlanView plan={analyze.plan!} />
          </div>
        ) : null}

        {showCrunching ? (
          <div className="chat-empty" role="status" aria-live="polite">
            <p>{COPY.chat.crunching}</p>
          </div>
        ) : null}

        {analyze.error ? (
          <div className="chat-message chat-message--error">
            <p>{analyze.error}</p>
          </div>
        ) : null}

        {!analyze.streaming && !hasPlan && !analyze.error ? (
          <div className="chat-empty chat-empty--centered" role="status">
            <p>{COPY.chat.emptyNoResponse}</p>
            <p>{COPY.chat.emptyNoResponseHint}</p>
          </div>
        ) : null}

        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            role={message.role}
            content={message.content}
            streaming={message.streaming}
            citations={message.citations}
          />
        ))}
      </div>

      <ChatComposer
        onSend={handleSend}
        onStop={followup.stop}
        streaming={followup.streaming}
      />

      {analyze.metadata ? (
        <ModelFooter metadata={analyze.metadata} elapsedMs={elapsedMs} />
      ) : null}
    </div>
  );
}

// Re-export PlanView so existing tests targeting this module keep finding
// the named export they expect.
export { PlanView };
