import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  CanvasResponse,
  PlanMetadata,
} from '../../types';
import type { Conversation } from '../../lib/conversationStore';
import { COPY } from '../../copy';
import { ChatPane } from './ChatPane';

const MOCK_CANVAS: CanvasResponse = {
  pan_masked: 'ABCPS****A',
  customer_id: 'cust_001',
  as_of_date: '2026-07-25',
  score_hero: {
    score: 715,
    band: 'Good',
    score_min: 300,
    score_max: 900,
    previous_score_1mo: 730,
    previous_score_3mo: 740,
    score_change_1mo: -15,
    score_change_3mo: -25,
    score_trend: 'falling',
    band_progress: 0.3,
    bands: [
      { name: 'Poor', min_score: 300, max_score: 579 },
      { name: 'Fair', min_score: 580, max_score: 699 },
      { name: 'Good', min_score: 700, max_score: 749 },
      { name: 'Very Good', min_score: 750, max_score: 799 },
      { name: 'Excellent', min_score: 800, max_score: 900 },
    ],
  },
  score_trend: {
    points: [
      { label: '3 months ago', score: 740 },
      { label: '1 month ago', score: 730 },
      { label: 'Now', score: 715 },
    ],
    trend: 'falling',
    change_3mo: -25,
    annotation: 'Score dropped 25 points in 3 months',
  },
  utilization: {
    overall_utilization: 0.572,
    total_balance_paise: 515000,
    total_credit_limit_paise: 900000,
    target_utilization: 0.30,
    paydown_to_target_paise: 245000,
    cards: [
      {
        account_id: 'acc_001_1',
        display_name: 'HDFC Millennia',
        balance_paise: 420000,
        credit_limit_paise: 600000,
        utilization: 0.70,
        is_maxed: false,
        is_unused: false,
        paydown_to_target_paise: 240000,
      },
    ],
    top_card_account_id: 'acc_001_1',
    callout: 'Highest card: HDFC Millennia at 70%.',
  },
  payment_heatmap: {
    cells: [],
    months_on_time: 24,
    months_total: 24,
    pct_on_time: 1.0,
    worst_status: 0,
    most_recent_late_period: null,
    summary: '24/24 on time',
  },
  labels: {
    pan_masked: 'ABCPS****A',
    customer_id: 'cust_001',
    score: 715,
    score_band: 'Good',
    as_of_date: '2026-07-25',
    total_labels: 32,
    n_fired: 0,
    labels: [],
    fired_by_severity: { critical: [], warning: [], ok: [], excellent: [], info: [] },
  },
  first_name: 'Anjali',
};

const PLAN = {
  current_situation: 'Pay down the maxed-out card.',
  top_actions: [
    {
      title: 'Pay Down High Utilization Card',
      why: 'It is at 70% utilisation.',
      steps: ['Pay ₹2,40,000 today.'],
      when_youll_see_results: '1-2 billing cycles',
    },
  ],
  what_to_avoid: ['Do not close the card.'],
};

const METADATA: PlanMetadata = {
  model: 'gpt-4o-mini-2024-07-18',
  prompt_tokens: 4129,
  completion_tokens: 535,
};

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'conv-1',
    panMasked: 'ABCPS****A',
    firstName: 'Anjali',
    incomeInr: 75000,
    canvas: MOCK_CANVAS,
    initialPlan: PLAN,
    initialMetadata: METADATA,
    elapsedMs: 17_600,
    turns: [],
    createdAt: '2026-07-25T00:00:00.000Z',
    updatedAt: '2026-07-25T00:00:00.000Z',
    ...overrides,
  };
}

function flush() {
  return act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

function makeFetch(routes: Record<string, () => string>) {
  return vi.fn().mockImplementation((url: string) => {
    const factory = routes[url];
    if (!factory) {
      return Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' }),
      });
    }
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(factory()));
        controller.close();
      },
    });
    return Promise.resolve({
      ok: true,
      status: 200,
      body: stream,
      headers: new Headers({ 'content-type': 'text/event-stream' }),
    });
  });
}

const CHAT_OK_SSE = (text: string) =>
  [
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: metadata\ndata: ${JSON.stringify({
      model: 'gpt-4o-mini-2024-07-18',
      prompt_tokens: 500,
      completion_tokens: 80,
    })}\n\n`,
    `event: citations\ndata: ${JSON.stringify({ citations: [{ label_id: 'maxed_out' }] })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_GUARDRAIL_SSE = () =>
  [
    `event: guardrail\ndata: ${JSON.stringify({ verdict: 'out_of_scope', reason: 'in' })}\n\n`,
    `event: token\ndata: ${JSON.stringify({ content: COPY.chat.outOfScope })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_REPLACE_SSE = () =>
  [
    `event: token\ndata: ${JSON.stringify({ content: 'I can help. ' })}\n\n`,
    `event: guardrail\ndata: ${JSON.stringify({ verdict: 'out_of_scope', reason: 'post_check' })}\n\n`,
    `event: replace\ndata: ${JSON.stringify({ content: COPY.chat.outOfScope })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_ERROR_SSE = () =>
  [`event: error\ndata: ${JSON.stringify({ message: 'embedding failed' })}\n\n`].join('');

describe('ChatPane follow-up flow', () => {
  let onUpdate: (conv: Conversation) => void;

  beforeEach(() => {
    onUpdate = vi.fn();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the composer with the placeholder', async () => {
    vi.stubGlobal('fetch', makeFetch({}));
    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();
    expect(
      screen.getByPlaceholderText(COPY.composer.placeholder),
    ).toBeInTheDocument();
  });

  it('hydrates the initial plan from the conversation without calling /api/analyze', async () => {
    const fetchSpy = vi.fn(() => Promise.resolve({
      ok: true,
      status: 200,
      body: null,
      headers: new Headers({ 'content-type': 'text/event-stream' }),
    }));
    vi.stubGlobal('fetch', fetchSpy);

    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    expect(screen.getByText(/Pay Down High Utilization Card/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('shows the model metadata footer on the initial plan', async () => {
    vi.stubGlobal('fetch', makeFetch({}));
    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    expect(screen.getByText(/Model:/)).toBeInTheDocument();
    expect(
      screen.getByText('gpt-4o-mini-2024-07-18'),
    ).toBeInTheDocument();
  });

  it('sends a follow-up and renders the streamed assistant reply with citation pills', async () => {
    let chatBody: any;
    const fetchImpl = vi.fn().mockImplementation((url: string, init?: { body?: string }) => {
      if (url === '/api/chat') {
        chatBody = init?.body ? JSON.parse(init.body) : null;
      }
      const sse = url === '/api/chat' ? CHAT_OK_SSE('Pay down the card [maxed_out].') : '';
      if (!sse) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: 'Not found' }),
        });
      }
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.composer.placeholder),
      { target: { value: 'what should I pay off first?' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.composer.sendAria }));

    await waitFor(() => {
      expect(
        screen.getByText(/Pay down the card/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText('Maxed Out')).toBeInTheDocument();
    expect(chatBody.message).toBe('what should I pay off first?');
  });

  it('renders the guardrail redirect copy when /api/chat emits a guardrail event', async () => {
    const fetchImpl = vi.fn().mockImplementation((url: string) => {
      const sse = url === '/api/chat' ? CHAT_GUARDRAIL_SSE() : '';
      if (!sse) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: 'Not found' }),
        });
      }
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.composer.placeholder),
      { target: { value: 'should I invest in stocks?' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.composer.sendAria }));

    await waitFor(() => {
      expect(screen.getByText(COPY.chat.outOfScope)).toBeInTheDocument();
    });
  });

  it('replaces a partial reply when the post-check fires', async () => {
    const fetchImpl = vi.fn().mockImplementation((url: string) => {
      const sse = url === '/api/chat' ? CHAT_REPLACE_SSE() : '';
      if (!sse) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: 'Not found' }),
        });
      }
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.composer.placeholder),
      { target: { value: 'help me' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.composer.sendAria }));

    await waitFor(() => {
      expect(screen.getByText(COPY.chat.outOfScope)).toBeInTheDocument();
    });
  });

  it('renders an error bubble when the chat stream errors', async () => {
    const fetchImpl = vi.fn().mockImplementation((url: string) => {
      const sse = url === '/api/chat' ? CHAT_ERROR_SSE() : '';
      if (!sse) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: 'Not found' }),
        });
      }
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(
      <ChatPane
        conversation={makeConversation()}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.composer.placeholder),
      { target: { value: 'help me' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.composer.sendAria }));

    await waitFor(() => {
      expect(screen.getByText('embedding failed')).toBeInTheDocument();
    });
  });

  it('locks the composer with the disabled hint when there is no initial plan', async () => {
    vi.stubGlobal('fetch', makeFetch({}));
    render(
      <ChatPane
        conversation={makeConversation({ initialPlan: null, initialMetadata: null, canvas: null })}
        onConversationUpdate={onUpdate}
        canRunAnalyzer={false}
      />,
    );
    await flush();

    expect(
      screen.getByPlaceholderText(COPY.composer.disabledHint),
    ).toBeInTheDocument();
  });
});
