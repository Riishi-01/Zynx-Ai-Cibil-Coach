import { useCallback, useEffect, useState } from 'react';

import { COPY } from '../copy';
import type {
  CanvasResponse,
  PartialCoachPlan,
  PlanMetadata,
} from '../types';
import {
  type Conversation,
  clearTurns,
  deleteConversation,
  getConversation,
  listConversations,
  saveConversation,
} from '../lib/conversationStore';
import { ChatPane } from '../components/chat/ChatPane';
import { ConfirmDialog } from '../components/dialogs/ConfirmDialog';
import { CanvasPane } from '../components/canvas/CanvasPane';
import { Dock } from '../components/dock/Dock';
import { InputForm } from '../components/input/InputForm';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { getTurnstileSiteKey } from '../lib/turnstile';

function buildId() {
  return Math.random().toString(36).slice(2);
}

function emptyConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: '',
    panMasked: '',
    firstName: null,
    incomeInr: 0,
    canvas: null,
    initialPlan: null,
    initialMetadata: null,
    elapsedMs: 0,
    turns: [],
    createdAt: now,
    updatedAt: now,
  };
}

/**
 * Shell layout: dock on the left, IDLE form or session view on the right.
 *
 * State flow:
 *   IDLE  — user fills the form.
 *   SUBMIT — POST /api/analyze streams back canvas + plan + metadata,
 *            we synthesise the analyzer's first response into the
 *            conversation store, then promote it to active.
 *   VIEW — ChatPane hydrates from the persisted conversation; /api/analyze
 *            is never called again for the same conversation.
 *
 * Clearing a chat keeps the analyzer's initial plan intact.
 */
export function Analyzer() {
  const [conversations, setConversations] = useState<Conversation[]>(() =>
    listConversations(),
  );
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  );
  const [isStreamingAnalyze, setStreamingAnalyze] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const reducedMotion = useReducedMotion();

  const activeConversation = activeConversationId
    ? getConversation(activeConversationId) ?? null
    : null;

  const persistConversation = useCallback((conv: Conversation) => {
    saveConversation(conv);
    setConversations(listConversations());
  }, []);

  const refreshConversations = useCallback(() => {
    setConversations(listConversations());
  }, []);

  const handleNewConversation = useCallback((conv: Conversation) => {
    persistConversation(conv);
    setActiveConversationId(conv.id);
  }, [persistConversation]);

  const handlePickConversation = useCallback((id: string) => {
    setActiveConversationId(id);
  }, []);

  const handleDeleteConversation = useCallback(
    (id: string) => {
      deleteConversation(id);
      refreshConversations();
      if (activeConversationId === id) setActiveConversationId(null);
    },
    [activeConversationId, refreshConversations],
  );

  const handleClearAllHistory = useCallback(() => {
    // Wipe every stored conversation but keep the active session's open
    // record; clearing whole history isn't destructive when the user is
    // mid-session.
    const active = activeConversationId;
    setConversations((prev) => {
      prev.forEach((conv) => {
        if (conv.id !== active) deleteConversation(conv.id);
      });
      return active ? prev.filter((conv) => conv.id === active) : [];
    });
    refreshConversations();
  }, [activeConversationId, refreshConversations]);

  // Subscribed turn handler — Conversation.turns lists in the most recent
  // order. We expect callers to append in order.
  const handleConversationUpdate = useCallback(
    (updated: Conversation) => {
      persistConversation(updated);
    },
    [persistConversation],
  );

  const handleHome = useCallback(() => {
    // Home does not clear the active conversation — it merely hides the
    // session. The dock history still lists it.
    setActiveConversationId(null);
  }, []);

  const handleClearChatRequest = useCallback(() => {
    if (!activeConversation) return;
    if (activeConversation.turns.length === 0) return;
    setConfirmClear(true);
  }, [activeConversation]);

  const handleClearChatConfirm = useCallback(() => {
    if (!activeConversation) return;
    const cleared = clearTurns(activeConversation.id) ?? activeConversation;
    persistConversation(cleared);
    setConfirmClear(false);
  }, [activeConversation, persistConversation]);

  const handleClearChatCancel = useCallback(() => {
    setConfirmClear(false);
  }, []);

  const handleSubmit = useCallback(
    async (values: { pan: string; incomeInr: number; turnstileToken: string | null }) => {
      const turnstileToken = values.turnstileToken;
      setStreamingAnalyze(true);

      const id = buildId();
      const now = new Date().toISOString();
      const initial: Conversation = {
        ...emptyConversation(),
        id,
        panMasked: '',
        firstName: null,
        incomeInr: values.incomeInr,
        createdAt: now,
        updatedAt: now,
      };

      try {
        const response = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            pan: values.pan,
            income: values.incomeInr,
            turnstile_token: turnstileToken ?? undefined,
          }),
        });

        if (!response.ok || !response.body) {
          const errBody = await response.json().catch(() => ({
            detail: `HTTP ${response.status}`,
          }));
          throw new Error(errBody.detail ?? `HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let canvas: CanvasResponse | null = null;
        let plan: PartialCoachPlan = {};
        let metadata: PlanMetadata | null = null;
        const startedAt = performance.now();

        const persist = (overrides: Partial<Conversation> = {}) => {
          if (!plan && !canvas) return;
          const draft: Conversation = {
            ...initial,
            canvas,
            initialPlan: plan,
            initialMetadata: metadata,
            panMasked: canvas?.pan_masked ?? '',
            firstName: canvas?.first_name?.trim() || initial.firstName,
            elapsedMs: metadata
              ? Math.max(0, performance.now() - startedAt)
              : 0,
            turns: [],
            ...overrides,
          };
          handleNewConversation(draft);
        };

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';
          for (const frame of frames) {
            if (!frame.trim()) continue;
            const lines = frame.split('\n');
            let event = '';
            let data = '';
            for (const line of lines) {
              if (line.startsWith('event: ')) event = line.slice(7);
              else if (line.startsWith('data: ')) data = line.slice(6);
            }
            if (!event || !data) continue;
            try {
              const parsed = JSON.parse(data);
              switch (event) {
                case 'canvas':
                  canvas = parsed;
                  persist();
                  break;
                case 'plan_delta':
                  plan = { ...plan, ...parsed };
                  persist();
                  break;
                case 'metadata':
                  metadata = parsed;
                  persist();
                  break;
                case 'done':
                  setStreamingAnalyze(false);
                  return;
                case 'error':
                  setStreamingAnalyze(false);
                  throw new Error(parsed.message ?? 'Chat error');
                default:
                  break;
              }
            } catch {
              // Skip malformed frames.
            }
          }
        }
      } catch (err) {
        // Surface a transient error state in the analyzer reducer for
        // future IDLE view. For now, log; the page can show a banner.
        // eslint-disable-next-line no-console
        console.error('Analyze failed', err);
        setStreamingAnalyze(false);
      }
    },
    [handleNewConversation],
  );

  return (
    <div className="analyzer">
      <Dock
        onHome={handleHome}
        onPickConversation={handlePickConversation}
        onClearAllHistory={handleClearAllHistory}
        onDeleteConversation={handleDeleteConversation}
        onClearChat={handleClearChatRequest}
        conversations={conversations}
        activeConversationId={activeConversationId}
        inSession={activeConversationId !== null}
        hasChatTurns={!!activeConversation && activeConversation.turns.length > 0}
      />

      <main className="analyzer-main">
        {activeConversationId === null ? (
          <div className="analyzer-idle">
            <h1 className="analyzer-brand">{COPY.analyzer.brand}</h1>
            <InputForm
              onSubmit={handleSubmit}
              submitting={isStreamingAnalyze}
              reducedMotion={reducedMotion}
            />
            {isStreamingAnalyze ? (
              <div className="analyzer-status" role="status" aria-live="polite">
                Crunching the numbers…
              </div>
            ) : null}
          </div>
        ) : activeConversation ? (
          <SessionView
            conversation={activeConversation}
            onConversationUpdate={handleConversationUpdate}
          />
        ) : null}
      </main>

      <ConfirmDialog
        open={confirmClear}
        title={COPY.message.clearChatConfirmTitle}
        body={COPY.message.clearChatConfirmBody}
        confirmLabel={COPY.message.clearChatConfirmConfirm}
        cancelLabel={COPY.message.clearChatConfirmCancel}
        onConfirm={handleClearChatConfirm}
        onCancel={handleClearChatCancel}
      />
    </div>
  );
}

interface SessionViewProps {
  conversation: Conversation;
  onConversationUpdate: (conv: Conversation) => void;
}

function SessionView({ conversation, onConversationUpdate }: SessionViewProps) {
  const [canvasData, setCanvasData] = useState<CanvasResponse | null>(
    conversation.canvas,
  );
  const turnstileSiteKey = getTurnstileSiteKey();

  // Hydrate the canvas from the conversation prop on first mount.
  useEffect(() => {
    if (canvasData === null && conversation.canvas) {
      setCanvasData(conversation.canvas);
    }
  }, [canvasData, conversation.canvas]);

  return (
    <div className="analyzer-panes">
      <section
        className="analyzer-pane analyzer-pane--chat"
        aria-label={COPY.analyzer.chatSection}
      >
        <ChatPane
          conversation={conversation}
          onConversationUpdate={onConversationUpdate}
          canRunAnalyzer={false}
          turnstileToken={turnstileSiteKey}
        />
      </section>
      <section
        className="analyzer-pane analyzer-pane--canvas"
        aria-label={COPY.analyzer.canvasSection}
      >
        <CanvasPane data={canvasData} />
      </section>
    </div>
  );
}
