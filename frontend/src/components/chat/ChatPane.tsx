import { useCallback, useEffect, useRef, useState } from 'react';

import { COPY } from '../../copy';
import { useStream } from '../../hooks/useStream';
import type { ChatCitation, PlanMetadata } from '../../types';
import type {
  Conversation,
  ConversationTurn,
} from '../../lib/conversationStore';
import { ChatComposer } from './ChatComposer';
import { ChatMessage, type ChatMessageData } from './ChatMessage';
import { PlanView } from './PlanView';

interface ChatPaneProps {
  /** When present, hydrates from the saved conversation instead of calling /api/analyze. */
  conversation: Conversation;
  /** Fired after every local mutation. The page persists via the conversation store. */
  onConversationUpdate: (conv: Conversation) => void;
  /** Suppress the initial /api/analyze call when the parent supplies a fresh conversation. */
  canRunAnalyzer: boolean;
  turnstileToken?: string | null;
}

const NEAR_BOTTOM_PX = 80;

function buildId() {
  return Math.random().toString(36).slice(2);
}

function toHistoryTurns(turns: ConversationTurn[]) {
  return turns
    .filter(
      (turn) => !turn.role || turn.role === 'user' || turn.role === 'assistant',
    )
    .filter((turn) => typeof turn.content === 'string')
    .map((turn) => ({ role: turn.role, content: turn.content }));
}

/**
 * The chat pane: hydrated plan + follow-up messages + composer.
 *
 * Designed to be paired with the dock. On mount, it renders whatever is
 * already in ``conversation``: the initial plan (with its own
 * MessageMetadata), then each prior follow-up turn. No /api/analyze call
 * is issued when the conversation is hydrated.
 *
 * When ``canRunAnalyzer`` is true (e.g. the user just submitted the form)
 * the parent can call ``triggerInitialAnalysis``; this pane waits for
 * the resulting conversation to land before mounting.
 */
export function ChatPane({
  conversation,
  onConversationUpdate,
  canRunAnalyzer,
  turnstileToken,
}: ChatPaneProps) {
  const followup = useStream();
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeMessageIdRef = useRef<string | null>(null);
  const userScrolledUpRef = useRef(false);
  const activeRequestStartRef = useRef<number | null>(null);
  const activeAccumulatorRef = useRef('');

  // Capturing the conversation prop in a ref so callbacks see the latest
  // version without re-binding each tick.
  const conversationRef = useRef(conversation);
  useEffect(() => {
    conversationRef.current = conversation;
  }, [conversation]);

  // Hydrate the message list from the conversation every time the
  // conversation prop changes (initial mount + history item picked).
  const [hydratedId, setHydratedId] = useState(conversation.id);
  const [initialMessages, setInitialMessages] = useState<ChatMessageData[]>(() =>
    conversation.initialPlan
      ? [
          {
            id: 'initial-plan',
            role: 'assistant' as const,
            content: '',
            plan: conversation.initialPlan,
            metadata: conversation.initialMetadata ?? undefined,
            elapsedMs: conversation.elapsedMs,
          },
        ]
      : [],
  );
  const [turns, setTurns] = useState<ChatMessageData[]>(() =>
    conversation.turns.map<ChatMessageData>((turn, idx) => ({
      id: `turn-${conversation.id}-${idx}`,
      role: turn.role,
      content: turn.content,
      metadata: turn.metadata,
      elapsedMs: turn.elapsedMs,
      citations: turn.citations,
    })),
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hydratedId === conversation.id) return;
    setHydratedId(conversation.id);
    setError(null);
    setTurns(
      conversation.turns.map<ChatMessageData>((turn, idx) => ({
        id: `turn-${conversation.id}-${idx}`,
        role: turn.role,
        content: turn.content,
        metadata: turn.metadata,
        elapsedMs: turn.elapsedMs,
        citations: turn.citations,
      })),
    );
    setInitialMessages(
      conversation.initialPlan
        ? [
            {
              id: 'initial-plan',
              role: 'assistant' as const,
              content: '',
              plan: conversation.initialPlan,
              metadata: conversation.initialMetadata ?? undefined,
              elapsedMs: conversation.elapsedMs,
            },
          ]
        : [],
    );
    activeMessageIdRef.current = null;
    activeAccumulatorRef.current = '';
  }, [conversation, hydratedId]);

  function patchActiveMessage(updater: (m: ChatMessageData) => ChatMessageData) {
    const id = activeMessageIdRef.current;
    if (!id) return;
    setTurns((prev) =>
      prev.map((m) => (m.id === id ? updater(m) : m)),
    );
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isNearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    if (userScrolledUpRef.current && !isNearBottom) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, initialMessages]);

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

  const finalizeActive = useCallback(
    (updates: Partial<ChatMessageData> = {}) => {
      const id = activeMessageIdRef.current;
      if (!id) return;
      const messageId = id;
      const finalMessage = turns.find((m) => m.id === messageId);
      if (!finalMessage) return;
      setTurns((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, ...updates, streaming: false } : m)),
      );
      const finalContent = updates.content ?? finalMessage.content;
      const finalMetadata = updates.metadata ?? finalMessage.metadata;
      const finalCitations = updates.citations ?? finalMessage.citations;
      const finalElapsedMs = updates.elapsedMs ?? finalMessage.elapsedMs;
      const cleaned: ConversationTurn = { role: 'assistant', content: finalContent };
      if (finalMetadata) cleaned.metadata = finalMetadata;
      if (finalCitations && finalCitations.length > 0) {
        cleaned.citations = finalCitations;
      }
      if (typeof finalElapsedMs === 'number') {
        cleaned.elapsedMs = finalElapsedMs;
      }
      onConversationUpdate({
        ...conversation,
        turns: [...conversation.turns, cleaned],
      });
      activeMessageIdRef.current = null;
      activeAccumulatorRef.current = '';
      activeRequestStartRef.current = null;
    },
    [turns, conversation, onConversationUpdate],
  );

  const handleFollowupToken = useCallback((chunk: string) => {
    if (!activeMessageIdRef.current) return;
    activeAccumulatorRef.current = activeAccumulatorRef.current + chunk;
    patchActiveMessage((m) => ({
      ...m,
      content: m.content + chunk,
    }));
  }, []);

  const handleFollowupCitations = useCallback((citations: ChatCitation[]) => {
    patchActiveMessage((m) => ({ ...m, citations }));
  }, []);

  const handleFollowupGuardrail = useCallback((info: { verdict: string }) => {
    if (info.verdict !== 'out_of_scope') return;
    if (!activeMessageIdRef.current) return;
    const redirect = COPY.chat.outOfScope;
    activeAccumulatorRef.current = redirect;
    patchActiveMessage((m) => ({
      ...m,
      content: redirect,
      citations: undefined,
      streaming: false,
    }));
    // Persist as a finished turn so the redirect survives reopen.
    const conversationUpdate: ConversationTurn = { role: 'assistant', content: redirect };
    onConversationUpdate({
      ...conversation,
      turns: [...conversation.turns, conversationUpdate],
    });
    activeMessageIdRef.current = null;
    activeAccumulatorRef.current = '';
  }, [conversation, onConversationUpdate]);

  const handleFollowupReplace = useCallback((content: string) => {
    if (!activeMessageIdRef.current) return;
    activeAccumulatorRef.current = content;
    patchActiveMessage((m) => ({
      ...m,
      content,
      citations: undefined,
      streaming: false,
    }));
    onConversationUpdate({
      ...conversation,
      turns: [...conversation.turns, { role: 'assistant', content }],
    });
    activeMessageIdRef.current = null;
    activeAccumulatorRef.current = '';
  }, [conversation, onConversationUpdate]);

  const handleFollowupMetadata = useCallback((md: PlanMetadata) => {
    if (!activeMessageIdRef.current) return;
    const elapsedMs = activeRequestStartRef.current
      ? Math.max(0, performance.now() - activeRequestStartRef.current)
      : undefined;
    patchActiveMessage((m) => ({
      ...m,
      metadata: md,
      ...(elapsedMs !== undefined ? { elapsedMs } : {}),
    }));
  }, []);

  useEffect(() => {
    if (!followup.error) return;
    const id = activeMessageIdRef.current;
    if (!id) return;
    setTurns((prev) =>
      prev.map((m) =>
        m.id === id
          ? {
              ...m,
              role: 'error',
              content: followup.error ?? 'Error',
              streaming: false,
            }
          : m,
      ),
    );
    onConversationUpdate({
      ...conversation,
      turns: [
        ...conversation.turns,
        { role: 'user', content: '' },
        {
          role: 'assistant',
          content: followup.error ?? 'Error',
        },
      ],
    });
    activeMessageIdRef.current = null;
    activeAccumulatorRef.current = '';
    setError(followup.error);
  }, [followup.error, conversation, onConversationUpdate]);

  useEffect(() => {
    if (!followup.done) return;
    const id = activeMessageIdRef.current;
    if (!id) return;
    const finalContent = activeAccumulatorRef.current;
    const elapsed = activeRequestStartRef.current
      ? Math.max(0, performance.now() - activeRequestStartRef.current)
      : undefined;
    patchActiveMessage((m) => ({
      ...m,
      streaming: false,
      ...(finalContent ? { content: finalContent } : {}),
      ...(elapsed !== undefined ? { elapsedMs: elapsed } : {}),
    }));
    finalizeActive({});
  }, [followup.done, finalizeActive]);

  const handleSend = useCallback(
    (message: string) => {
      if (followup.streaming) return;
      const assistantId = buildId();
      activeMessageIdRef.current = assistantId;
      const startedAt = performance.now();
      activeRequestStartRef.current = startedAt;
      activeAccumulatorRef.current = '';
      setTurns((prev) => [
        ...prev,
        { id: buildId(), role: 'user', content: message },
        { id: assistantId, role: 'assistant', content: '', streaming: true },
      ]);
      onConversationUpdate({
        ...conversation,
        turns: [...conversation.turns, { role: 'user', content: message }],
      });

      const history = toHistoryTurns(conversation.turns);
      followup.send(
        '/api/chat',
        {
          pan: conversation.panMasked || '',
          message,
          history,
          turnstile_token: turnstileToken ?? undefined,
        },
        {
          onToken: handleFollowupToken,
          onCitations: handleFollowupCitations,
          onGuardrail: handleFollowupGuardrail,
          onReplace: handleFollowupReplace,
          onMetadata: handleFollowupMetadata,
        },
      );
    },
    [
      followup,
      conversation,
      turnstileToken,
      handleFollowupToken,
      handleFollowupCitations,
      handleFollowupGuardrail,
      handleFollowupReplace,
      handleFollowupMetadata,
      onConversationUpdate,
    ],
  );

  const hasInitialPlan = !!conversation.initialPlan;
  const canChat = hasInitialPlan;
  const showCrunching = canRunAnalyzer && initialMessages.length === 0 && !error;

  return (
    <div className="chat-pane">
      <div className="chat-messages" ref={scrollRef} aria-live="polite">
        {showCrunching ? (
          <div className="chat-empty" role="status" aria-live="polite">
            <p>{COPY.chat.crunching}</p>
          </div>
        ) : null}

        {initialMessages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}

        {turns.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}

        {!canRunAnalyzer && !hasInitialPlan && initialMessages.length === 0 && turns.length === 0 ? (
          <div className="chat-empty chat-empty--centered" role="status">
            <p>{COPY.chat.emptyNoResponse}</p>
            <p>{COPY.chat.emptyNoResponseHint}</p>
          </div>
        ) : null}
      </div>

      <ChatComposer
        onSend={handleSend}
        onStop={followup.stop}
        streaming={followup.streaming}
        disabled={!canChat}
      />
    </div>
  );
}

// Re-export PlanView so existing tests targeting this module keep finding
// the named export they expect.
export { PlanView };
